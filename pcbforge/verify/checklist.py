"""verify.checklist — verificação pré-fabricação (F2 — V-plane, M6).

Checklist independente que lê a pasta da placa (design/, kicad/, outputs/,
verify/) e devolve o veredito item por item:

  erc        → erc_report.json sem erros (V01, Plano Mestre §9/§13)
  drc        → drc_report.json 0 bloqueadores e 0 desconexões (V02)
  courtyard  → 0 sobreposições e 0 cruzamentos no placement (regra dura F0)
  catalogo   → todos os footprints do design aptos no catálogo (F1) ou
               peça LCSC baixada (libcache com .step)
  zip        → ZIP Gerbers íntegro (zipfile.testzip) com Edge_Cuts, drill,
               job e ≥1 arquivo de cobre (X01)
  camadas    → perfil vs camadas de cobre declaradas (V05 — "copper layers: N")

Nunca re-roda roteador nem KiCad: lê os relatórios já produzidos — o build
falha ANTES de exportar quando ERC/DRC ≠ 0 (regra de ouro §13.1), então
placa com zip existente tem relatórios congelados.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from pcbforge import paths

USER = paths.root()


def _json_seguro(caminho: Path) -> dict:
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _item(id_: str, ok: bool, detalhe: str) -> dict:
    return {"id": id_, "ok": bool(ok), "detalhe": detalhe}


def _layout_do_pcb(pasta_kicad: Path, nome: str, netlist: dict) -> dict | None:
    """Lê posições (x, y, rot) em frame do arquivo direto do .kicad_pcb.

    kiutils não reabre .kicad_pcb pós-SES (bug conhecido F0) — parse restrito.
    """
    pcb = pasta_kicad / f"{nome}.kicad_pcb"
    if not pcb.is_file():
        return None
    import re

    txt = pcb.read_text(encoding="utf-8", errors="replace")
    ops: dict[str, tuple[float, float, int]] = {}
    for bloco in re.split(r'\n\s*\(footprint ', txt)[1:]:
        ref = re.search(r'\(property "Reference" "([^"]+)"\)', bloco)
        at = re.search(r'\(at (-?[\d.]+) (-?[\d.]+)(?: (-?[\d.]+))?\)', bloco)
        if ref and at:
            x, y = float(at.group(1)), float(at.group(2))
            ang = int(float(at.group(3) or 0))
            ops[ref.group(1)] = (x, y, ang)
    return {c["ref"]: ops[c["ref"]] for c in netlist.get("components", [])
            if c["ref"] in ops}


def checklist_pre_fab(pasta: Path, nome: str | None = None) -> dict:
    """Devolve {"nome", "pronto": bool, "itens": [...], "texto": str}."""
    pasta = Path(pasta)
    nome = nome or pasta.name
    itens: list[dict] = []

    import yaml
    try:
        netlist = _json_seguro(pasta / "design" / "netlist.json")
        perfil = yaml.safe_load(
            (pasta / "design" / "board_profile.yaml").read_text(encoding="utf-8")) or {}
    except Exception as e:  # relatório, não crash (§9)
        netlist, perfil = {}, {}

    # ——— ERC (V01) ———
    erc = _json_seguro(pasta / "verify" / "erc_report.json")
    erc_erros = sum(1 for v in erc.get("violations", [])
                    if v.get("severity", "error") in ("error", None))
    itens.append(_item("erc", bool(erc) and erc_erros == 0,
                       f"ERC: {erc_erros} erro(s)" if erc else "erc_report.json ausente"))

    # ——— DRC (V02) ———
    drc = _json_seguro(pasta / "verify" / "drc_report.json")
    viol = drc.get("violations", [])
    bloqueadores = sum(1 for v in viol if v.get("severity", "error") in ("error", None))
    desconexas = len(drc.get("unconnected_items", []))
    itens.append(_item("drc", bool(drc) and bloqueadores == 0 and desconexas == 0,
                       f"DRC: {bloqueadores} bloqueador(es), {desconexas} desconexão(ões)"
                       if drc else "drc_report.json ausente"))

    # ——— Courtyard + planaridade (regra dura F0) ———
    try:
        from pcbforge.core import placement as pl
        layout = _layout_do_pcb(pasta / "kicad", nome, netlist)
        if netlist and layout:
            conges = pl.contar_conflitos(pl.coords_pads(netlist, layout)[1])
            cruzes = pl.contar_cruzamentos(netlist, layout)
        else:
            conges, cruzes = 0, 0
        ok_cyu = conges == 0 and cruzes == 0
        itens.append(_item("courtyard", ok_cyu,
                           f"placement: {conges} sobreposição(ões), {cruzes} cruzamento(s)"))
    except Exception as e:  # relatório, não crash (§9)
        itens.append(_item("courtyard", False, f"falha na checagem: {e}"))

    # ——— Catálogo (F1) ———
    try:
        from pcbforge.parts import catalogo
        faltam = []
        libcache = USER / "libcache" / "lcsc"
        for c in netlist.get("components", []):
            fp = c.get("footprint_ref", "")
            apto = catalogo.apto(fp)
            if not apto and ":" in fp:
                lib, alvo = fp.split(":", 1)
                if lib == "LCSC":
                    # peça baixada: .kicad_mod presente no libcache + .step do MESMO id
                    for mod in libcache.glob(f"*/{alvo}.kicad_mod"):
                        id_dir = mod.parent.stem
                        apto = bool(list(libcache.glob(f"{id_dir}.3dshapes/*.step")))
                        break
            if not apto:
                faltam.append(fp)
        itens.append(_item("catalogo", not faltam,
                           f"{len(faltam)} footprint(s) fora do catálogo: "
                           f"{', '.join(faltam[:5])}" if faltam else "todos os footprints aptos"))
    except Exception as e:
        itens.append(_item("catalogo", False, f"falha na checagem: {e}"))

    # ——— ZIP Gerbers íntegro (X01) ———
    zips = sorted((pasta / "outputs").glob("*-v1-[12]c-*.zip"))
    zip_ok, zip_detalhe = False, "nenhum ZIP em outputs/"
    if zips:
        try:
            with zipfile.ZipFile(zips[-1]) as z:
                nomes = z.namelist()
                ruim = z.testzip()
                tem_borda = any("Edge_Cuts" in n for n in nomes)
                tem_drill = any(n.endswith(".drl") for n in nomes)
                tem_job = any(n.endswith(".gbrjob") for n in nomes)
                cobre = [n for n in nomes if n.endswith((".gtl", ".gbt", ".gbl"))]
                ok = ruim is None and tem_borda and tem_drill and tem_job and cobre
                zip_detalhe = (f"zip {zips[-1].name}: {len(nomes)} arquivos, "
                               f"Edge_Cuts={'ok' if tem_borda else 'FALTA'}, "
                               f"drill={'ok' if tem_drill else 'FALTA'}, "
                               f"job={'ok' if tem_job else 'FALTA'}, "
                               f"fases de cobre {len(cobre)}, "
                               f"integridade {'ok' if ruim is None else ruim}")
                zip_ok = ok
        except (zipfile.BadZipFile, OSError) as e:
            zip_detalhe = f"zip corrompido: {e}"
    itens.append(_item("zip", zip_ok, zip_detalhe))

    # ——— Camadas coerentes (V05) ———
    try:
        camadas_perfil = int((perfil or {}).get("stackup", {}).get("layers", 0))
        ok_camadas = camadas_perfil in (1, 2)
        itens.append(_item("camadas", ok_camadas,
                           f"copper layers: {camadas_perfil}"
                           + ("" if ok_camadas else " (pipeline v1 apóia 1–2 camadas)")))
    except Exception as e:
        itens.append(_item("camadas", False, f"falha na checagem: {e}"))

    pronto = all(i["ok"] for i in itens)
    texto = f"[{'✅' if pronto else '⛔'}] {nome} — checklist pré-fab:\n" + "\n".join(
        f"  {'✅' if i['ok'] else '❌'} {i['id']}: {i['detalhe']}" for i in itens)
    return {"nome": nome, "pronto": pronto, "itens": itens, "texto": texto}

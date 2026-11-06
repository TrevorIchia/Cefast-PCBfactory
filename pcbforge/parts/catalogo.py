"""parts.catalogo — índice dos footprints APTOS (F1 — limpa de componentes, M2).

Plano Mestre §6/§17 F1: respostas de colocação só usam os footprints aptos:
    apto = pads THT/SMD claros e numerados + modelo 3D `.step` existente no disco
    exceção documentada: MountingHole (furo puro, sem 3D por natureza)

Fonte de dados: `pcbforge/config/catalogo.json` (produzido por
`gerar_catalogo()` ou por `scripts/censo_footprints.py`).
"""
from __future__ import annotations

import json
import re
import time
from functools import lru_cache  # noqa: F401  (padrão do módulo)
from pathlib import Path

from pcbforge import paths

_sh = paths.kicad_shared() or Path("kicad_shared_nao_encontrado")
FOOTPRINTS_DIR = _sh / "footprints"
MODELS3D_DIR = _sh / "3dmodels"
CATALOGO_PATH = paths.root() / "pcbforge" / "config" / "catalogo.json"
# libs extras auditáveis (F14a — regra do usuário: só entra peça COM 3D real).
# Formato esperado: <pasta>/<Lib>.pretty/*.kicad_mod + <pasta>/<Lib>.3dshapes/*.step
EXTRA_DIR = paths.root() / "libcache" / "kicad-extra"


def _bases_extra() -> list[tuple[Path, Path]]:
    """Bases elegíveis no EXTRA_DIR: [(raiz_pretty, raiz_3d)] — cobre o layout
    padrão KiCad (`<Lib>.pretty` direto) e o da Espressif (`footprints/` +
    `3dmodels/`)."""
    if not EXTRA_DIR.is_dir():
        return []
    saida = []
    for sub in sorted(EXTRA_DIR.iterdir()):
        if not sub.is_dir():
            continue
        for fpd in (sub, sub / "footprints"):
            if fpd.is_dir() and any(fpd.glob("*.pretty")):
                m3d = None
                for base in (sub, sub.parent):     # Espressif: 3dmodels no raiz do repo
                    if (base / "3dmodels").is_dir():
                        m3d = base / "3dmodels"
                        break
                saida.append((fpd, m3d or sub))
                break
    return saida

# exceção documentada (Plano Mestre §17 F1): furo puro sem modelo 3D
LISENCES_SEM_3D = ("MountingHole",)

_PAD_NUM = re.compile(r'\(pad "([^"]*)"\s+(smd|thru_hole|np_thru_hole|connect)\b')
_MODEL = re.compile(r'\(model "([^"]+)"')

_catalogo: dict[str, dict] | None = None


def _scan_footprints() -> dict[str, dict]:
    """Varre o diretório oficial + bases extras auditadas; devolve {ref: ficha}."""
    cat: dict[str, dict] = {}
    if FOOTPRINTS_DIR.is_dir():
        _scan_base(FOOTPRINTS_DIR, MODELS3D_DIR, cat)
    for fpd, m3d in _bases_extra():      # F14a: libs 3rd-party com 3D auditado
        _scan_base(fpd, m3d, cat)
    return cat


def _scan_base(footprints_root: Path, models3d_root: Path,
               cat: dict[str, dict]) -> None:
    """Varre UMA raíz de footprints + 3dmodels no mesmo padrão do KiCad."""
    libs = sorted(d for d in footprints_root.iterdir() if d.suffix == ".pretty")
    for lib_dir in libs:
        lib = lib_dir.stem
        for mod in sorted(lib_dir.glob("*.kicad_mod")):
            try:
                txt = mod.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            tipos = _PAD_NUM.findall(txt)
            if not tipos:
                continue  # sem pad algum — não é componente
            pinos = [(n, t) for n, t in tipos if t in ("smd", "thru_hole")]
            puro_furo = not pinos
            if puro_furo and not lib.startswith(LISENCES_SEM_3D):
                continue
            step = False
            for m in _MODEL.finditer(txt):
                caminho_mod = m.group(1).strip()
                if caminho_mod.startswith("${KICAD10_3DMODEL_DIR}/"):
                    if (models3d_root / caminho_mod.split("/", 1)[1]).is_file():
                        step = True
                        break
                elif models3d_root != MODELS3D_DIR:
                    # lib 3rd-party (ex.: Espressif): nome do .STEP findable em qualquer
                    # subpasta de 3dshapes da raiz — case-insensitive e em massa pequena
                    achou = [p for p in models3d_root.rglob(caminho_mod.rsplit("/", 1)[-1])
                             if p.suffix.lower() == ".step"]
                    if achou:
                        step = True
                        break
            if not step and not puro_furo:
                continue  # exigência: 3D no disco (exceção: MountingHole)
            smd = sum(1 for _n, t in tipos if t == "smd")
            tht = sum(1 for _n, t in tipos if t == "thru_hole")
            cat[f"{lib}:{mod.stem}"] = {
                "pads": len(pinos),
                "smd_pads": smd,
                "tht_pads": tht,
                "tipo": ("smd" if smd >= tht else "tht"),
                "puro_furo": puro_furo,
                "step": step,
            }
    return cat


def gerar_catalogo(destino: Path = CATALOGO_PATH) -> dict:
    """Gera e salva catalogo.json; devolve os metadados do censo."""
    cat = _scan_footprints()
    smd = sum(1 for v in cat.values() if v["tipo"] == "smd")
    dados = {
        "_meta": {
            "fonte": str(FOOTPRINTS_DIR),
            "criterio": "pads THT/SMD claros + modelo .step no disco; exceção: MountingHole",
            "data_censo": time.strftime("%Y-%m-%d %H:%M"),
            "total": len(cat),
            "smd": smd,
            "tht": len(cat) - smd,
        },
        "footprints": cat,
    }
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(dados, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
    global _catalogo
    _catalogo = None  # invalida cache
    return dados["_meta"]


def carregar() -> dict[str, dict]:
    """Carrega o catálogo (cache); regenera automaticamente se faltar o JSON."""
    global _catalogo
    if _catalogo is not None:
        return _catalogo
    if not CATALOGO_PATH.is_file():
        meta = gerar_catalogo()
        print(f"catalogo.json ausente — regenerado ({meta['total']} aptos)", file=__import__('sys').stderr)
    dados = json.loads(CATALOGO_PATH.read_text(encoding="utf-8"))
    _catalogo = dados.get("footprints", {})
    return _catalogo


def info(footprint_ref: str) -> dict | None:
    """Ficha do footprint no catálogo; None se não existe/não apto."""
    return carregar().get(footprint_ref)


def apto(footprint_ref: str) -> bool:
    """True se o footprint está no catálogo (i.e., é apto para colocação)."""
    return footprint_ref in carregar()


def alternativas(footprint_ref: str) -> list[str]:
    """Outros footprints aptos da MESMA lib e família (ex.: R_0402, R_0805).

    Família = primeiro segmento do nome antes dos sufixos de tamanho; ordena por
    semelhança de nome decrescente.
    """
    cat = carregar()
    lib, _, nome = footprint_ref.partition(":")
    if not lib or not nome:
        return []
    familia = nome.split("_")[0]
    datas = [f"{lib}:{n}" for _r, n in (p.split(":", 1) for p in cat if p.startswith(lib + ":"))
             if n.split("_")[0] == familia and f"{lib}:{n}" != footprint_ref]
    return sorted(datas)


@lru_cache(maxsize=256)
def _similaridade(a: str, b: str) -> int:
    """# de caracteres iniciais/sufixos iguais — heurística barata de proximidade."""
    comum = sum(1 for x, y in zip(a.split("_"), b.split("_")) if x == y)
    return comum * 8 + int(a[:4] == b[:4])


def melhor_alternativa(footprint_ref: str) -> str | None:
    """Alternativa mais parecida do mesmo catálogo (None se não há)."""
    cands = alternativas(footprint_ref)
    if not cands:
        return None
    _, _, nome = footprint_ref.partition(":")
    return max(cands, key=lambda c: _similaridade(nome, c.partition(":")[2]))

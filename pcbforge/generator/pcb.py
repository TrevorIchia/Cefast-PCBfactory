"""generator.pcb — netlist neutra + board_profile → .kicad_pcb (função `gerar_pcb`).

Regras do Plano Mestre §7:
  - outline da placa conforme size_mm (G03)
  - furos de montagem nos cantos conforme mounting (G04)
  - camadas conforme stackup (face simples ⇒ nada roteado em B.Cu, §4.3)
  - footprints VÊM da biblioteca oficial, posicionados por heurística §7.1
  - pads recebem as nets da netlist (base para DRC)
"""
from __future__ import annotations

from pathlib import Path

from kiutils.footprint import Footprint
from kiutils.board import Board
from kiutils.items.common import Net, Position
from kiutils.items.gritems import GrLine

from pcbforge import paths

FOOTPRINTS_DIR = Path("/Applications/KiCad.app/Contents/SharedSupport/footprints")
# F7: raiz universal (paths.root honra PCBFORGE_ROOT) — o antigo
# parent.parent/"pcbforge" dobrava o pacote (bug latente: só projetos NOVOS
# esbarravam, rebuilds reutilizavam o .kicad_pro existente)
TEMPLATE_PRO = paths.root() / "pcbforge" / "assets" / "template.kicad_pro"


def _dir_footprints() -> Path:
    """Pasta das .pretty — paths.kicad_shared() (F5) com fallback ao caminho fixo."""
    shared = paths.kicad_shared()
    if shared is not None and (shared / "footprints").is_dir():
        return shared / "footprints"
    return FOOTPRINTS_DIR


def _footprint_caminho(footprint_ref: str) -> Path | None:
    """'Lib:Nome' → caminho do .kicad_mod (oficial; fallback libcache/kicad-extra)."""
    if not footprint_ref or ":" not in footprint_ref:
        return None
    lib, nome = footprint_ref.split(":", 1)
    p = _dir_footprints() / f"{lib}.pretty" / f"{nome}.kicad_mod"
    if p.exists():
        return p
    # F14a/F14c: lib EXTRA do repo (Espressif etc.) — binding com 3D real
    # auditado (§20.2 do Plano Mestre); a oficial equivalente NÃO tem .step.
    extra = paths.root() / "libcache/kicad-extra/footprints" / f"{lib}.pretty" / f"{nome}.kicad_mod"
    return extra if extra.exists() else None


def _nets_da_netlist(netlist: dict) -> list[Net]:
    """Nets com nome vêm primeiro (1..N); unconnected é a 0."""
    nomes = [c.get("net_name", "") for c in netlist.get("connections", []) if c.get("net_name")]
    vistos: list[str] = []
    for nome in nomes:
        if nome not in vistos:
            vistos.append(nome)
    return [Net(number=0, name="")] + [Net(number=i, name=n) for i, n in enumerate(vistos, start=1)]


def _posicoes_iniciais(comps: list[dict], w: float, h: float) -> dict[str, tuple[float, float]]:
    """Posicionamento v2 (§7.1):
    - 'pos_mm' explícito na netlist vence (permite comparar layouts — teste de ida e volta)
    - conectores empilham na borda esquerda; CI no centro; resto em duas fileiras.
    """
    pos: dict[str, tuple[float, float]] = {}
    conectores = [c for c in comps if c["type"] == "conector"]
    ci = [c for c in comps if c["type"] in ("ci", "mcu")]
    resto = [c for c in comps if c not in conectores and c not in ci]

    for i, comp in enumerate(conectores):
        pos[comp["ref"]] = (8.0, h / 2.0 + (i - (len(conectores) - 1) / 2.0) * 14.0)
    for i, comp in enumerate(ci):
        pos[comp["ref"]] = (w / 2.0 + 14.0 * i, h / 2.0)
    meio = (len(resto) + 1) // 2
    for i, comp in enumerate(resto[:meio]):
        pos[comp["ref"]] = (16.0 + 7.0 * i, h / 2.0 - 12.0)
    for i, comp in enumerate(resto[meio:]):
        pos[comp["ref"]] = (16.0 + 7.0 * i, h / 2.0 + 12.0)

    for comp in comps:
        if mm := comp.get("pos_mm"):
            pos[comp["ref"]] = (float(mm[0]), float(mm[1]))
    return pos


def _normaliza_textos_fp(fp: Footprint, ref: str) -> None:
    """Mistério 1 (F14c): libs extras (ex.: Espressif ESP32-C3-MINI-1) trazem
    `fp_text reference "REF**"` — e o GerReference do KiCad prefere esse texto
    gráfico ao property "Reference"; o DSN/SES saía com 18x REF** e pins
    inominados quebravam a net do Freerouting. Footprints oficiais KiCad≥6
    usam `fp_text user "${REFERENCE}"` (template, inócuo). Normaliza o texto
    do item reference para a REF do componente."""
    for gi in fp.graphicItems or []:
        if type(gi).__name__ == "FpText" and getattr(gi, "type", "") == "reference":
            gi.text = ref


def _gira_pads(fp: Footprint, ang: int) -> None:
    """Mistério 2 (F14c): no `.kicad_pcb` o ângulo do token `(at x y a)` do pad
    é a orientação ABSOLUTA da forma — o próprio pcbnew escreve (relativo da
    lib + rot_fp) e mantém o pad position local (golden 31-10 via api do
    KiCad; 2 falsificações do modelo relativo-a-footprint). Copiando o
    `.kicad_mod` cru, um footprint a 90° mantinha o shape desalinhado:
    pads adjacentes encostavam (gap 0.0 mm) → 44 violações pin-a-pin
    pré-roteamento em TODAS as seeds/tentativas. Corrige: somar a rotação do
    footprint ao ângulo de cada pad."""
    ang = int(ang) % 360
    if ang == 0:
        return
    for pad in fp.pads:
        base = int(pad.position.angle or 0) % 360
        pad.position.angle = (base + ang) % 360


def _furos_de_montagem(board: Board, perfil: dict) -> int:
    """Adiciona furos M3 nos cantos conforme perfil.mounting (G04). Devolve n adicionados."""
    mont = perfil.get("mounting") or {}
    if not mont.get("corners"):
        return 0
    w = float(perfil.get("size_mm", {}).get("w"))
    h = float(perfil.get("size_mm", {}).get("h"))
    margem = float(mont.get("margin", 3))
    cantos: list[tuple[float, float]] = {
        1: [(w - margem, h - margem)],
        2: [(margem, h - margem), (w - margem, h - margem)],
        4: [(margem, margem), (w - margem, margem), (w - margem, h - margem), (margem, h - margem)],
    }.get(int(mont["corners"]), [])

    fp_path = FOOTPRINTS_DIR / "MountingHole.pretty" / "MountingHole_3.2mm_M3.kicad_mod"
    if not fp_path.exists():
        raise FileNotFoundError(f"furo de montagem padrão não achado: {fp_path}")
    for i, (x, y) in enumerate(cantos, start=1):
        fp = Footprint.from_file(str(fp_path))
        fp.position = Position(X=x, Y=y, angle=0)
        fp.properties["Reference"] = f"H{i}"
        fp.properties["Value"] = "M3"
        board.footprints.append(fp)
    return len(cantos)


def aplicar_regras_projeto(pasta_kicad: Path, nome_proj: str, perfil: dict) -> Path:
    """Grava .kicad_pro com rules + netclass conforme board_profile.

    No KiCad 8+/10 as constraints DRC (min_track_width etc.) vivem no
    <proj>.kicad_pro, não no .kicad_pcb. Sem isto, o DRC usa o default
    0.2/0.2 e a promessa do perfil (ex. 0.25) nunca é checada.
    """
    import json

    pro = pasta_kicad / f"{nome_proj}.kicad_pro"
    if not pro.exists():
        import shutil
        pro.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(TEMPLATE_PRO, pro)

    dados = json.loads(pro.read_text())
    trace = float(perfil.get("min_trace_mm", 0.25) or 0.25)
    clar = float(perfil.get("min_clearance_mm", 0.25) or 0.25)
    via = float(perfil.get("min_via_mm", 0.5) or 0.5)
    # furo mínimo 0,2mm (F14c): é o mínimo FABRICÁVEL — o default 0,3 do KiCad
    # brigava com o array de vias térmicas oficial do ESP32-WROOM-32 (drill
    # 0,2), que é padrão Espressif e suportado pelas montadoras.
    hole = float(perfil.get("min_hole_mm", 0.2) or 0.2)

    # O bloco que o DRC lê é board.design_settings.rules (schema KiCad ≥8):
    rules = dados.setdefault("board", {}).setdefault("design_settings", {}).setdefault("rules", {})
    rules["min_track_width"] = trace
    rules["min_connection"] = trace
    rules["min_clearance"] = clar
    rules["min_via_diameter"] = via
    rules["min_through_hole_diameter"] = hole
    # sustentáculo mal-criado de senhas antigas: não viver aqui
    dados["board"].pop("rules", None)

    classe = (dados.setdefault("net_settings", {}).setdefault("classes", [{}]))[0]
    classe["track_width"] = trace
    classe["clearance"] = clar
    classe["via_diameter"] = via

    pro.write_text(json.dumps(dados, indent=2))
    return pro


def gerar_pcb(netlist: dict, perfil: dict, pasta_kicad: Path, nome_proj: str,
              layout: dict[str, tuple[float, float, int]] | None = None) -> Path:
    """Cria .kicad_pcb esquelético (sem rotas). Falha com exceção legível."""
    stackup = perfil["stackup"]
    size = perfil.get("size_mm", {})
    w = float(size.get("w", 50))
    h = float(size.get("h", 30))
    camadas = int(stackup.get("layers", 2))
    if camadas < 1:
        raise ValueError("perfil de placa inválido: layers < 1")

    b = Board.create_new()
    b.nets = _nets_da_netlist(netlist)

    # G03: outline retangular (v2 aceitará DXF)
    if perfil.get("outline_shape", "retângulo") != "retângulo":
        raise NotImplementedError("outline não-retangular entra na v2")
    for (x1, y1, x2, y2) in [(0, 0, w, 0), (w, 0, w, h), (w, h, 0, h), (0, h, 0, 0)]:
        b.graphicItems.append(GrLine(start=Position(X=x1, Y=y1), end=Position(X=x2, Y=y2),
                                     layer="Edge.Cuts", width=0.1))

    # G04: furos de montagem pelos cantos
    _furos_de_montagem(b, perfil)

    # Componentes (layout otimizado vence quando fornecido: (x, y, ângulo))
    posicoes = _posicoes_iniciais(netlist.get("components", []), w, h)
    if layout is None:
        layout = {c["ref"]: (*posicoes.get(c["ref"], (w / 2, h / 2)), 0)
                  for c in netlist.get("components", [])}
    for comp in netlist.get("components", []):
        ref = comp["ref"]
        caminho = _footprint_caminho(comp.get("footprint_ref", ""))
        if not caminho:
            raise FileNotFoundError(f"footprint não encontrado: {comp.get('footprint_ref')!r} (componente {ref})")
        fp = Footprint.from_file(str(caminho))
        # KiCad ≥9: zone de footprint com wildcard "*.Cu" é REJEITADA no load do
        # board ("items on undefined layers (*.Cu)" — kicad-cli rc=3). Prova
        # 30-10 por bisseção: sem-zone ✓ | layer "F.Cu" ✓ | multi
        # ("F.Cu" "B.Cu") ✓ | "*\.Cu" ✗ (com ou sem aspas). Pads aceitam
        # wildcard; zona precisa de cobres EXPLÍCITOS conforme o stackup.
        cobre = ["F.Cu", "B.Cu"][:camadas]
        for z in fp.zones:
            if list(z.layers or []) == ["*.Cu"]:
                z.layers = list(cobre)
        # F14c: componente fora do layout (ponte nova que o annealing ainda
        # não conhece)? Vence o pos_mm da netlist — centro burro nunca.
        x, y, ang = layout.get(ref, (*posicoes.get(ref, (w / 2, h / 2)), 0))
        fp.position = Position(X=float(x), Y=float(y), angle=int(ang) % 360)
        _gira_pads(fp, ang)
        _normaliza_textos_fp(fp, ref)
        fp.properties["Reference"] = ref
        fp.properties["Value"] = comp.get("value", "")
        b.footprints.append(fp)

    # Nets nos pads
    por_ref: dict[str, Footprint] = {}
    for fp in b.footprints:
        por_ref[fp.properties.get("Reference", "")] = fp
    net_por_nome = {n.name: n for n in b.nets if n.name}
    for conn in netlist.get("connections", []):
        nome = conn.get("net_name", "")
        if not nome:
            continue
        net = net_por_nome.get(nome)
        if net is None:
            raise ValueError(f"net '{nome}' ausente da lista de nets")
        for lado in ("a", "b"):
            ref, pin = conn[lado]["ref"], str(conn[lado]["pin"])
            alvo = por_ref.get(ref)
            if alvo is None:
                raise ValueError(f"componente {ref} não está no board")
            pad = next((p for p in alvo.pads if str(p.number) == pin), None)
            if pad is None:
                raise ValueError(f"pino {pin} não existe em {ref} ({alvo.entryName})")
            pad.net = net

    pasta_kicad.mkdir(parents=True, exist_ok=True)
    saida = pasta_kicad / f"{nome_proj}.kicad_pcb"
    b.filePath = str(saida)
    b.to_file()
    return saida

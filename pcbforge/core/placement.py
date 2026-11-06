"""core.placement — otimizador de posicionamento pré-roteamento (Plano §7.1).

Filosofia do usuário (2026-10-28): trilhas as curtas possíveis. Em vez de
executar o roteador em tentativa e erro, ESTIMAMOS o roteamento sem executar
(comprimento retangular da árvore mínima de cada net sobre as coordenadas REAIS
dos pads, com penalidade de sobreposição) e giramos/movemos componentes
buscando o mínimo. Freerouting depois só confirma e aperta os cantos.

Cada componente pode girar 0/90/180/270° — a função de pad (x,y) rota junto,
mantendo coerência elétrica (nets continuam vindo/indo por número de pino).
"""
from __future__ import annotations

import json
import math
import random
import subprocess
from collections import defaultdict
from itertools import combinations
from pathlib import Path

from pcbforge import paths

FOOTPRINTS_DIR = paths.footprints_dir()  # libs oficiais por SO (mac/linux/windows)
KI_BRIDGE = Path(__file__).resolve().parent / "courtyard_kibridge.py"

_cache_pad: dict[str, dict[str, tuple[float, float, float]]] = {}
_cache_courtyard: dict[str, tuple[float, float, float, float]] = {}


def _dirs_footprints() -> list[Path]:
    """Pasta oficial + bases extras auditadas (F14a) — nesta ordem de busca."""
    dirs = []
    shared = paths.kicad_shared()
    if shared is not None and (shared / "footprints").is_dir():
        dirs.append(shared / "footprints")
    else:
        fp = FOOTPRINTS_DIR  # paths-based; None se KiCad ausente
        if fp is not None:
            dirs.append(fp)
    from pcbforge.parts import catalogo
    for fpd, _m3d in catalogo._bases_extra():
        dirs.append(fpd)
    return dirs


def _caminho_kicad_mod(footprint_ref: str) -> Path | None:
    """Localiza `<lib>.pretty/<nome>.kicad_mod` na oficial e nas extras."""
    lib, nome = footprint_ref.split(":", 1)
    for pasta in _dirs_footprints():
        caminho = pasta / f"{lib}.pretty" / f"{nome}.kicad_mod"
        if caminho.is_file():
            return caminho
    return None


def pads_do_footprint(footprint_ref: str) -> dict[str, tuple[float, float, float]]:
    """{pin: (x, y, tamanho)} em mm relativos ao origin do footprint (.kicad_mod oficial)."""
    if footprint_ref in _cache_pad:
        return _cache_pad[footprint_ref]
    if not footprint_ref or ":" not in footprint_ref:
        raise ValueError(
            f"footprint_ref '{footprint_ref or '(vazio)'}' inválido no placement: "
            "componente sem footprint resolvido — revisar a prévia/brain "
            "(§13.1, U05); nunca inventar (§13.3)")
    from kiutils.footprint import Footprint

    lib, nome = footprint_ref.split(":", 1)
    caminho = _caminho_kicad_mod(footprint_ref)
    if caminho is None:
        raise ValueError(
            f"footprint '{footprint_ref}' não encontrado no disco (oficial+extras): "
            "catálogo e disco divergem — rode o re-censo (§19.2)")
    fp = Footprint.from_file(str(caminho))
    pads: dict[str, tuple[float, float, float]] = {}
    for pad in fp.pads:
        t = pad.size
        tx = float(t.X) if t is not None else 0.0
        ty = float(t.Y) if t is not None else 0.0
        pads[str(pad.number)] = (float(pad.position.X), float(pad.position.Y), max(tx, ty))
    _cache_pad[footprint_ref] = pads
    return pads


def courtyards_via_pcbnew(refs: list[str]) -> dict[str, tuple[float, float, float, float]]:
    """Lote: courtyards REAIS de N footprints em UM subprocess do Python do KiCad.

    F7 — fonte primária: `FOOTPRINT.GetCourtyard(F_CrtYd)`, o MESMO parser do
    DRC do KiCad ⇒ zero divergência guard↔DRC (o kiutils não parseia geometria
    de fórmula do `.kicad_mod` — falso-negativo do J2 provado na F0). Footprint
    sem courtyard declarado fica FORA do dict — o chamador decide o fallback.
    Falha (sem KiCad/timeout) ⇒ dict vazio, nunca crash (§9).
    """
    faltam = [r for r in dict.fromkeys(refs) if r and r not in _cache_courtyard]
    if not faltam:
        return {}
    ki = paths.ki_python()
    if ki is None:
        return {}
    try:
        r = subprocess.run([ki, str(KI_BRIDGE), str(_dirs_footprints()[0]), *faltam],
                           capture_output=True, text=True, timeout=120)
    except (subprocess.TimeoutExpired, OSError):
        return {}
    linha = next((ln for ln in (r.stdout or "").splitlines()
                  if ln.startswith("PCBFORGE_JSON ")), None)
    if linha is None:
        return {}
    try:
        bruto = json.loads(linha.split(" ", 1)[1])
    except json.JSONDecodeError:
        return {}
    saida: dict[str, tuple[float, float, float, float]] = {}
    for ref, bbox in bruto.items():
        if isinstance(bbox, list) and len(bbox) == 4:
            saida[ref] = (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
            _cache_courtyard[ref] = saida[ref]
    return saida


def courtyard_do_footprint(footprint_ref: str) -> tuple[float, float, float, float]:
    """Bbox do courtyard (layer F.CrtYd) relativo ao origin do footprint.

    É a área MINÍMA de sobreposição — não usar só os pads (D2×R2 passou no
    custo e o DRC barrou). Fontes em ordem (F7): (1) pcbnew GetCourtyard via
    ponte (mesmo parser do DRC); (2) parse kiutils do `.kicad_mod`;
    (3) pads + halo 0,25mm (último recurso).
    """
    if footprint_ref in _cache_courtyard:
        return _cache_courtyard[footprint_ref]
    if courtyards_via_pcbnew([footprint_ref]):
        return _cache_courtyard[footprint_ref]
    from kiutils.footprint import Footprint

    lib, nome = footprint_ref.split(":", 1)
    caminho = _caminho_kicad_mod(footprint_ref)
    if caminho is None:
        raise ValueError(
            f"footprint '{footprint_ref}' não encontrado no disco (oficial+extras): "
            "catálogo e disco divergem — rode o re-censo (§19.2)")
    fp = Footprint.from_file(str(caminho))
    minx = miny = math.inf
    maxx = maxy = -math.inf
    # courtyard pode ser fp_line, fp_rect, fp_circle ou fp_poly — aceitar tudo
    formas_geo = (
        list(getattr(fp, "lines", []))
        + list(getattr(fp, "rects", []))
        + list(getattr(fp, "circles", []))
        + list(getattr(fp, "polys", []))
        + list(getattr(fp, "arcs", []))
    )
    for it in formas_geo:
        if "CrtYd" not in (getattr(it, "layer", "") or ""):
            continue
        xs, ys = [], []
        s = getattr(it, "start", None)
        e = getattr(it, "end", None)
        c = getattr(it, "center", None)
        r = getattr(it, "radius", 0.0) or 0.0
        w = getattr(it, "width", 0.0) or 0.0
        if s is not None and e is not None:
            xs += [s.X, e.X]; ys += [s.Y, e.Y]
        elif c is not None:
            xs += [c.X - r - w / 2, c.X + r + w / 2]
            ys += [c.Y - r - w / 2, c.Y + r + w / 2]
        pts = getattr(it, "points", None)
        if pts:
            xs += [p.X for p in pts]; ys += [p.Y for p in pts]
        if not xs:
            continue
        minx, miny = min(minx, min(xs)), min(miny, min(ys))
        maxx, maxy = max(maxx, max(xs)), max(maxy, max(ys))
    if minx == math.inf:
        # sem courtyard declarado: pads + halo conservador de 0,25mm
        caixas = pads_do_footprint(footprint_ref)
        if not caixas:
            minx, miny, maxx, maxy = -0.5, -0.5, 0.5, 0.5
        else:
            minx = miny = math.inf
            maxx = maxy = -math.inf
            for _x, _y, tam in caixas.values():
                minx = min(minx, _x - tam / 2 - 0.25)
                miny = min(miny, _y - tam / 2 - 0.25)
                maxx = max(maxx, _x + tam / 2 + 0.25)
                maxy = max(maxy, _y + tam / 2 + 0.25)
    _cache_courtyard[footprint_ref] = (minx, miny, maxx, maxy)
    return _cache_courtyard[footprint_ref]


def _rot(c: tuple[float, float, float], ang: int) -> tuple[float, float, float]:
    """Gira pad (x,y,tam) em {0,90,180,270}°.

    Prova empírica (jig rotprobe 2026-10-28, DSN↔SES com Freerouting): no frame
    do arquivo (Y para baixo), se o footprint tem position.angle = A no KiCad o
    offset do pad obedece (x,y)→(y,−x) para A=90 (sentido horário visual).
    """
    ang %= 360
    x, y, t = c
    if ang == 90:
        return (y, -x, t)
    if ang == 180:
        return (-x, -y, t)
    if ang == 270:
        return (-y, x, t)
    return (x, y, t)


def coords_pads(netlist: dict, posicoes: dict[str, tuple[float, float, int]]) \
        -> tuple[dict[str, dict[str, tuple[float, float]]], dict[str, tuple[float, float, float, float]]]:
    """Devolve ({ref: {pin: (x,y)}}, {ref: bbox(x1,y1,x2,y2)}) em mm da placa."""
    loc: dict[str, dict[str, tuple[float, float]]] = {}
    caixas: dict[str, tuple[float, float, float, float]] = {}
    # F7: 1 subprocess do pcbnew para TODOS os courtyards (barato e coerente
    # com o DRC do KiCad); o loop abaixo apanha do cache.
    courtyards_via_pcbnew([c.get("footprint_ref") or ""
                           for c in netlist.get("components", [])])
    for comp in netlist.get("components", []):
        ref = comp["ref"]
        x0, y0, ang = posicoes[ref]
        loc[ref] = {}
        for pin, (px, py, tam) in pads_do_footprint(comp["footprint_ref"]).items():
            rx, ry, _ = _rot((px, py, tam), ang)
            loc[ref][pin] = (x0 + rx, y0 + ry)
        # bbox = courtyard do footprint (área física mínima), girado com o componente
        cx1, cy1, cx2, cy2 = courtyard_do_footprint(comp["footprint_ref"])
        cantos = [(cx1, cy1), (cx2, cy1), (cx2, cy2), (cx1, cy2)]
        rotas = [_rot((x, y, 0.0), ang) for x, y in cantos]
        minx = x0 + min(r[0] for r in rotas)
        maxx = x0 + max(r[0] for r in rotas)
        miny = y0 + min(r[1] for r in rotas)
        maxy = y0 + max(r[1] for r in rotas)
        caixas[ref] = (minx, miny, maxx, maxy)
    return loc, caixas


def mst_arestas(pontos: list[tuple[float, float]]) -> list[tuple[int, int, float]]:
    """MST (Prim) sobre pontos; devolve arestas (índice_a, índice_b, dist_manhattan)."""
    if len(pontos) < 2:
        return []
    dentro, fora = [0], list(range(1, len(pontos)))
    aretes: list[tuple[int, int, float]] = []
    while fora:
        melhor_i = melhor_ponto = melhor_d = None
        for i in dentro:
            for j in fora:
                d = abs(pontos[i][0] - pontos[j][0]) + abs(pontos[i][1] - pontos[j][1])
                if melhor_d is None or d < melhor_d:
                    melhor_i, melhor_ponto, melhor_d = i, j, d
        aretes.append((melhor_i, melhor_ponto, melhor_d))
        dentro.append(melhor_ponto)
        fora.remove(melhor_ponto)
    return aretes


def _mst_len(pontos: list[tuple[float, float]]) -> float:
    """Árvore geradora mínima retangular (Manhattan) via Prim — estimativa honesta."""
    return sum(d for _, _, d in mst_arestas(pontos))


def _nets(netlist: dict) -> dict[str, list[dict]]:
    """{net_name: [{ref,pin}, ...]} deduplicado, na ordem das conexões."""
    saida: dict[str, list[dict]] = {}
    vistos: set[tuple[str, str, str]] = set()
    for conn in netlist.get("connections", []):
        nome = conn.get("net_name", "")
        for lado in ("a", "b"):
            chave = (nome, conn[lado]["ref"], str(conn[lado]["pin"]))
            if chave not in vistos:
                vistos.add(chave)
                saida.setdefault(nome, []).append({"ref": conn[lado]["ref"], "pin": str(conn[lado]["pin"])})
    return saida


def contar_cruzamentos(netlist: dict, posicoes: dict[str, tuple[float, float, int]]) -> int:
    """Cruzamentos entre trilhas ESTIMADAS de nets diferentes.

    Motivação (F0, pesquisa 2026-10-28): em 1 camada um cruzamento de duas
    nets é IMPOSSÍVEL de rotear sem violação — o Freerouting deixa exatamente
    essas conexões presas (controle: 2 camadas roteia tudo). O placement
    precisa de topologia PLANA; aqui estimamos as arestas da MST de cada net
    (estrada em L retangular) e contamos interseções entre nets distintas.
    """
    pads, _ = coords_pads(netlist, posicoes)
    segs: dict[str, list[tuple[float, float, float, float]]] = defaultdict(list)
    for nome, membros in _nets(netlist).items():
        pts = [pads[m["ref"]][m["pin"]] for m in membros if m["pin"] in pads.get(m["ref"], {})]
        for ia, ib, _d in mst_arestas(pts):
            a, b = pts[ia], pts[ib]
            segs[nome].append((a[0], a[1], b[0], a[1]))  # braço horizontal
            segs[nome].append((b[0], b[1], b[0], b[1]))  # braço vertical
    nomes = sorted(segs)
    n = 0
    for i in range(len(nomes) - 1):
        for j in range(i + 1, len(nomes)):
            for s in segs[nomes[i]]:
                for t in segs[nomes[j]]:
                    if _segs_cruzam(s, t):
                        n += 1
    return n


def _segs_cruzam(s: tuple[float, float, float, float], t: tuple[float, float, float, float]) -> bool:
    """Interseção de dois segmentos alinhados aos eixos (não só encosto pontual)."""
    sh = abs(s[1] - s[3]) < 1e-9          # s horizontal?
    th = abs(t[1] - t[3]) < 1e-9
    sx1, sy1, sx2, sy2 = s
    tx1, ty1, tx2, ty2 = t
    if sh and th:
        if abs(sy1 - ty1) > 1e-9:
            return False
        return max(min(sx1, sx2), min(tx1, tx2)) < min(max(sx1, sx2), max(tx1, tx2)) - 1e-9
    if sh and not th:
        return _h_vs_v(sx1, sy1, sx2, tx1, ty1, ty2)
    if th and not sh:
        return _h_vs_v(tx1, ty1, tx2, sx1, sy1, sy2)
    # ambos verticais
    return False


def _h_vs_v(hx1, hy, hx2, vx, vy1, vy2) -> bool:
    """Horizontal (hx1,hy)-(hx2,hy) cruza vertical (vx,vy1)-(vx,vy2)?"""
    if not (min(hx1, hx2) < vx < max(hx1, hx2)):
        return False
    return min(vy1, vy2) < hy < max(vy1, vy2)


def contar_conflitos(caixas: dict[str, tuple[float, float, float, float]]) -> int:
    """Quantos pares de bbox de componentes se sobrepõem (folga 1.5mm já embutida?).

    Entrada direta de coords_pads(...)[1] — sem folga extra (um pouquinho de
    espaço de manobra entre pads já está contabilizado pelo tamanho do pad)."""
    refs = list(caixas)
    n = 0
    for i in range(len(refs)):
        for j in range(i + 1, len(refs)):
            a, b = caixas[refs[i]], caixas[refs[j]]
            if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                n += 1
    return n


def custo_total(netlist: dict, posicoes: dict[str, tuple[float, float, int]],
                w: float, h: float, folga: float = 2.0) -> float:
    """Comprimento MST retangular + penalidades (sobreposição, fora da placa e cruzamentos).

    Cruzamentos (F0): em face simples cada cruzamento entre nets é um caminho
    impossível — peso 120/mm eq. Por isso o custo já empurra o hill-climb para
    topologia plana antes de o Freerouting sequer ser chamado.
    """
    pads, caixas = coords_pads(netlist, posicoes)
    trilhas = 0.0
    for _, membros in _nets(netlist).items():
        pts = [pads[m["ref"]][m["pin"]] for m in membros if m["pin"] in pads.get(m["ref"], {})]
        trilhas += _mst_len(pts)

    penal = 0.0
    refs = list(caixas)
    for i in range(len(refs)):
        for j in range(i + 1, len(refs)):
            a, b = caixas[refs[i]], caixas[refs[j]]
            if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                penal += 60.0
    for x1, y1, x2, y2 in caixas.values():
        if x1 - folga < 0 or y1 - folga < 0 or x2 + folga > w or y2 + folga > h:
            penal += 500.0
    penal += 120.0 * contar_cruzamentos(netlist, posicoes)
    return trilhas + penal


def comprimento_estimado(netlist: dict, posicoes: dict[str, tuple[float, float, int]]) -> float:
    """Só o comprimento retangular das trilhas (sem penalidade) — p/ build.log."""
    pads, _ = coords_pads(netlist, posicoes)
    total = 0.0
    for _, membros in _nets(netlist).items():
        pts = [pads[m["ref"]][m["pin"]] for m in membros if m["pin"] in pads.get(m["ref"], {})]
        total += _mst_len(pts)
    return total


def _clamp_borda(netlist: dict, pos: dict[str, tuple[float, float, int]],
                 w: float, h: float, folga: float = 2.0) -> dict[str, tuple[float, float, int]]:
    """Empurra para dentro da placa quem fura a margem de borda (§7.1.6).

    F7: com courtyards REAIS (pcbnew, maiores que os falsos do kiutils) a grade
    inicial pode nascer fora da margem — e a penalidade 500 vira mínimo local
    do hill-climb (seed 3: trilhas +13mm presas fora da placa). O clamp é
    EXATO: o offset do bbox não depende da posição, uma passada resolve.
    """
    _, caixas = coords_pads(netlist, pos)          # também pré-carrega courtyards
    # F8: componente FIXO (âncora) não é clampado — bornier na borda com
    # entrada de fio pra fora CRUZA a margem de propósito (A7); empurrá-lo
    # quebrava a âncora em silêncio (sanduíche: J1 4.0→5.045, J2 56.0→53.635)
    fixos = {c["ref"] for c in netlist.get("components", []) if c.get("fixo")}
    saida = dict(pos)
    for ref, (x1, y1, x2, y2) in caixas.items():
        if ref in fixos:
            continue
        x0, y0, ang = saida[ref]
        dx = dy = 0.0
        if x1 < folga:
            dx = folga - x1
        elif x2 > w - folga:
            dx = (w - folga) - x2
        if y1 < folga:
            dy = folga - y1
        elif y2 > h - folga:
            dy = (h - folga) - y2
        if dx or dy:
            saida[ref] = (x0 + dx, y0 + dy, ang)
    return saida


def _fora_da_borda(netlist: dict, pos: dict[str, tuple[float, float, int]],
                   w: float, h: float, folga: float = 2.0) -> int:
    """Quantos componentes têm courtyard fora da margem de borda (§7.1.6).

    F7: usado como PORTA na aceitação do hill-climb e no passe final — nunca
    aceitar um estado que fure a borda (com courtyards reais do pcbnew o
    baralho de trocas pode enfiar um corpo grande num espaço pequeno).
    """
    _, caixas = coords_pads(netlist, pos)
    fixos = {c["ref"] for c in netlist.get("components", []) if c.get("fixo")}
    n = 0
    for ref, (x1, y1, x2, y2) in caixas.items():
        if ref in fixos:
            continue  # âncora proposital pode cruzar a margem (entrada de fio)
        if x1 < folga or y1 < folga or x2 > w - folga or y2 > h - folga:
            n += 1
    return n


def _caixas_furos(perfil: dict) -> list[tuple[float, float, float, float]]:
    """Bbox do courtyard de cada furo de montagem (mesmos cantos do G04).

    Os furos entram SÓ no gerador (_furos_de_montagem, DEPOIS do placement) —
    o otimizador não os via e encostava componentes no courtyard do M3
    (DRC courtyards_overlap, sanduíche H1xR1/H4xJ1 em 28-10-2026).
    """
    mont = perfil.get("mounting") or {}
    n = int(mont.get("corners") or 0)
    if not n:
        return []
    size = perfil.get("size_mm", {})
    w, h = float(size.get("w", 50)), float(size.get("h", 30))
    margem = float(mont.get("margin", 3))
    cantos = {
        1: [(w - margem, h - margem)],
        2: [(margem, h - margem), (w - margem, h - margem)],
        4: [(margem, margem), (w - margem, margem),
            (w - margem, h - margem), (margem, h - margem)],
    }.get(n, [])
    if not cantos:
        return []
    cx1, cy1, cx2, cy2 = courtyard_do_footprint("MountingHole:MountingHole_3.2mm_M3")
    return [(x + cx1, y + cy1, x + cx2, y + cy2) for x, y in cantos]


def _desencalhe_caixas(netlist: dict, melhor: dict, w: float, h: float,
                       fixos: set[str], furos: list | None = None,
                       passes: int = 3) -> dict:
    """Passe DETERMINÍSTICO de desencalhe por courtyard (F14c — irmandade do
    `_caixas_furos`/furos M3): pós-annealing, para cada par de courtyards que
    se intersecta: (1) empurra o MENOR (nunca `fixo`) para fora do maior pelo
    deslocamento mínimo AABB; (2) se o push só troca de vizinho (a borda do
    maior já encosta em outras peças — casamento do keepout de antena), tele-
    porta o menor para a FAIXA LIVRE: scan de grade fixa, zero random.
    `furos` (zona de furo `_caixas_furos`) também é respeitado: nenhum
    courtyard movido pode invadir um furo de montagem (caso real D1↔H4
    do semaforo). Nunca aceita jogada que piora (conflitos ou borda).
    Existe porque keepout de antena (ex.: ESP32-WROOM-32, court 48×41 mm com
    zona de antena) é restrição de ÁREA 2D — mais iterações/camadas não
    desencalham.
    """
    _foot = {c["ref"]: c.get("footprint_ref", "") for c in netlist.get("components", [])}

    def _caixa_de(ref: str, pos: tuple[float, float, int]) -> tuple:
        x0, y0, ang = pos
        cx1, cy1, cx2, cy2 = courtyard_do_footprint(_foot[ref])
        cantos = [(cx1, cy1), (cx2, cy1), (cx2, cy2), (cx1, cy2)]
        rotas = [_rot((x, y, 0.0), ang) for x, y in cantos]
        return (x0 + min(r[0] for r in rotas), y0 + min(r[1] for r in rotas),
                x0 + max(r[0] for r in rotas), y0 + max(r[1] for r in rotas))

    _furos = furos or []

    def _livre(cx2: dict, ref: str) -> bool:
        bm = cx2[ref]
        nos_outros = all(not (bm[0] < cx2[o][2] and cx2[o][0] < bm[2]
                              and bm[1] < cx2[o][3] and cx2[o][1] < bm[3])
                         for o in cx2 if o != ref)
        nos_furos = all(not (bm[0] < f[2] and f[0] < bm[2]
                             and bm[1] < f[3] and f[1] < bm[3])
                        for f in _furos)
        return nos_outros and nos_furos

    for _pass in range(passes):
        _, caixas = coords_pads(netlist, melhor)
        atuais = contar_conflitos(caixas)
        if atuais == 0:
            break
        jogada_feita = False
        for a, b in sorted(combinations(sorted(caixas), 2)):
            ba, bb = caixas[a], caixas[b]
            if not (ba[0] < bb[2] and bb[0] < ba[2]
                    and ba[1] < bb[3] and bb[1] < ba[3]):
                continue
            areas = {a: (ba[2]-ba[0])*(ba[3]-ba[1]),
                     b: (bb[2]-bb[0])*(bb[3]-bb[1])}
            menor = min((a, b), key=lambda r: (r in fixos, areas[r]))
            if menor in fixos:            # menor congelado: nenhum dos 2 move
                continue
            bm = caixas[menor]
            outro = bb if menor == a else ba
            # deslocamentos p/ sair do `outro` em cada direção (≥ solapa + 0,05)
            dxp, dxn = outro[2] + 0.05 - bm[0], bm[2] - (outro[0] - 0.05)
            dyp, dyn = outro[3] + 0.05 - bm[1], bm[3] - (outro[1] - 0.05)
            dx, dy = min(dxp, dxn), min(dyp, dyn)
            x, y, ang = melhor[menor]
            jogou = False

            def _c2_testada(npos: tuple) -> tuple[dict, dict]:
                c2 = {r: tuple(p) for r, p in melhor.items()}
                c2[menor] = npos
                cpose = _clamp_borda(netlist, c2, w, h)
                cx2 = {r: _caixa_de(r, cpose[r]) for r in caixas}
                return cpose, cx2

            for npos in ((x + (dxp if dxp <= dxn else -dxn), y, ang),
                         (x, y + (dyp if dyp <= dyn else -dyn), ang)):
                cpose, cx2 = _c2_testada(npos)
                if (_livre(cx2, menor)
                        and _fora_da_borda(netlist, cpose, w, h) == 0):
                    melhor = {r: tuple(p) for r, p in cpose.items()}
                    _, caixas = coords_pads(netlist, melhor)
                    jogou = jogada_feita = True
                    break
            if jogou:
                continue
            # estágio 2 — teleporte escaneado p/ faixa livre (casamento clássico:
            # push troca de vizinho). Grade fixa 2mm, linha por linha; pega o
            # PRIMEIRO lugar sem conflito nenhum p/ o menor (determinístico).
            for cyc in range(int(h) - 2, int(1), -2):
                for cxc in range(int(2), int(w - 2), 2):
                    cpose, cx2 = _c2_testada((float(cxc), float(cyc), ang))
                    if (_livre(cx2, menor)
                            and _fora_da_borda(netlist, cpose, w, h) == 0):
                        melhor = {r: tuple(p) for r, p in cpose.items()}
                        _, caixas = coords_pads(netlist, melhor)
                        jogou = jogada_feita = True
                        break
                if jogou:
                    break
            if not jogou:
                jogada_feita = True   # passa adiante — outros pares ainda podem
        if not jogada_feita:
            break
    return melhor


def otimizar(netlist: dict, perfil: dict, iteracoes: int = 300, seed: int = 7,
             posicoes_iniciais: dict | None = None) -> tuple[dict[str, tuple[float, float, int]], float, float]:
    """Hill-climb: gira ±90°, troca posições e desliza ±6mm minimizando custo_total.

    Devolve (melhor_layout, comprimento_antes, comprimento_depois) em mm.
    """
    from pcbforge.generator.pcb import _posicoes_iniciais  # seed heurística

    size = perfil.get("size_mm", {})
    w, h = float(size.get("w", 50)), float(size.get("h", 30))
    comps = netlist.get("components", [])

    # F8 (regra A3 pré-requisito): componente com "fixo": true fica ANCORADO
    # em pos_mm — o annealing não troca, não gira e não move (ex.: bornier
    # na borda com entrada de fio pra fora). Assuma pos dentro da margem.
    fixos = {c["ref"] for c in comps if c.get("fixo")}

    if posicoes_iniciais is None:
        grid = _posicoes_iniciais(comps, w, h)
        posicoes_iniciais = {c["ref"]: (grid[c["ref"]][0], grid[c["ref"]][1], 0) for c in comps}

    rnd = random.Random(seed)
    grid = _posicoes_iniciais(comps, w, h)
    atual = {}
    for c in comps:
        if c.get("pos_mm"):
            atual[c["ref"]] = (float(c["pos_mm"][0]), float(c["pos_mm"][1]), 0)
        else:
            atual[c["ref"]] = (grid[c["ref"]][0], grid[c["ref"]][1], 0)
    if posicoes_iniciais:
        atual = {c["ref"]: tuple(posicoes_iniciais[c["ref"]]) for c in comps}
        for c in comps:  # fixo com pos_mm vence qualquer posicoes_iniciais externo
            if c["ref"] in fixos and c.get("pos_mm"):
                atual[c["ref"]] = (float(c["pos_mm"][0]), float(c["pos_mm"][1]), 0)
    atual = _clamp_borda(netlist, atual, w, h)
    melhor = dict(atual)
    melhor_c = custo_total(netlist, melhor, w, h)
    c0 = comprimento_estimado(netlist, melhor)

    refs = [c["ref"] for c in comps if c["ref"] not in fixos]
    if not comps:
        raise ValueError(
            "otimizar: netlist sem componentes — placement impossível (§4.3.2b)")
    for _ in range(iteracoes):
        cand = {r: tuple(p) for r, p in melhor.items()}
        acao = rnd.random()
        if acao < 0.35 and len(refs) > 1:
            r1, r2 = rnd.sample(refs, 2)
            cand[r1], cand[r2] = (cand[r2][0], cand[r2][1], cand[r1][2]), \
                                 (cand[r1][0], cand[r1][1], cand[r2][2])
        elif acao < 0.75:
            r = rnd.choice(refs)
            x, y, ang = cand[r]
            cand[r] = (x, y, (ang + 90) % 360)
        else:
            r = rnd.choice(refs)
            x, y, ang = cand[r]
            cand[r] = (min(max(x + rnd.uniform(-6, 6), 4.0), w - 4.0),
                       min(max(y + rnd.uniform(-6, 6), 4.0), h - 4.0), ang)
        c2 = custo_total(netlist, cand, w, h)
        if c2 < melhor_c - 1e-9 and _fora_da_borda(netlist, cand, w, h) == 0:
            melhor, melhor_c = cand, c2

    # passe final: eliminar sobreposições aceitando o movimento que as reduz
    # (F7: o movimento TEM de manter o layout dentro da margem de borda —
    #  sem essa porta, seed 3 trocava conflito por violação de borda +500)
    _, caixas = coords_pads(netlist, melhor)
    for _ in range(200):
        base = contar_conflitos(caixas)
        if base == 0:
            break
        cruzados: set[str] = set()
        refs_cx = list(caixas)
        for i in range(len(refs_cx)):
            for j in range(i + 1, len(refs_cx)):
                a, b = caixas[refs_cx[i]], caixas[refs_cx[j]]
                if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                    cruzados.update((refs_cx[i], refs_cx[j]))
        movaveis = sorted(r for r in cruzados if r not in fixos)
        if not movaveis:
            break  # conflito só entre fixos — inviável aqui (guard do build rejeita a seed)
        melhor_jogada = None
        for _2 in range(60):
            c2_ = {r: tuple(p) for r, p in melhor.items()}
            for r in rnd.sample(movaveis, min(2, len(movaveis))):
                x, y, ang = c2_[r]
                c2_[r] = (min(max(x + rnd.uniform(-6, 6), 4.0), w - 4.0),
                          min(max(y + rnd.uniform(-6, 6), 4.0), h - 4.0), ang)
            _, cx2 = coords_pads(netlist, c2_)
            nov = contar_conflitos(cx2)
            dentro = _fora_da_borda(netlist, c2_, w, h) == 0
            if nov < base and dentro and (melhor_jogada is None or nov < melhor_jogada[0]):
                melhor_jogada = (nov, c2_, cx2)
        if melhor_jogada:
            _, melhor, caixas = melhor_jogada
        else:
            break

    # G04/DRC (sanduíche 28-10): furos de montagem viram keepout do placement —
    # intruso MÓVEL é desencalhado; intrusão de fixo é estrutural (âncora
    # contratada) e o DRC reporta honestamente no fim.
    furos = _caixas_furos(perfil)
    if furos:
        base_c = contar_conflitos(caixas)

        def _intrusoes(cx: dict) -> list[str]:
            return sorted(r for r, b in cx.items()
                          if r not in fixos
                          and any(b[0] < f[2] and f[0] < b[2]
                                  and b[1] < f[3] and f[1] < b[3] for f in furos))

        for _ in range(200):
            _, caixas = coords_pads(netlist, melhor)
            intr = _intrusoes(caixas)
            if not intr:
                break
            jogada = None
            for _2 in range(60):
                c2_ = {r: tuple(p) for r, p in melhor.items()}
                for r in rnd.sample(intr, min(2, len(intr))):
                    x, y, ang = c2_[r]
                    c2_[r] = (min(max(x + rnd.uniform(-6, 6), 4.0), w - 4.0),
                              min(max(y + rnd.uniform(-6, 6), 4.0), h - 4.0), ang)
                _, cx2 = coords_pads(netlist, c2_)
                if (_intrusoes(cx2) == []
                        and contar_conflitos(cx2) <= base_c
                        and _fora_da_borda(netlist, c2_, w, h) == 0):
                    jogada = {r: tuple(p) for r, p in c2_.items()}
            if jogada:
                melhor = jogada
            else:
                break

    # F14c: passe determinístico de desencalhe por courtyard — o annealing
    # não desencalha presas dentro de keepout de antena (área 2D); furos de
    # montagem também são keepout honesto (D1↔H4 do semaforo).
    melhor = _desencalhe_caixas(netlist, melhor, w, h, fixos, furos=furos)

    return melhor, c0, comprimento_estimado(netlist, melhor)

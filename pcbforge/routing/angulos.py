"""routing.angulos — regra B1 aplicada (pesquisa 28-10-2026 + 3ª rodada).

Fontes: NextPCB ("acid traps: traces joining at angles under OR AT 90
degrees"), Altium DFM (cunha de ângulo agudo prende etchant), e-e ("right
angle bends are made of two 45 degree bends"), NWES/Cadence (com etchant
moderno 90° é tolerável — mas agudo <90° segue sendo problema universal).
Política do pipeline (diretriz do usuário: "evitar ângulos retos... no
caso quinas"):

  - viragem AGUDA (interior <90°) → BLOQUEIO: nunca exportar (acid trap real);
  - viragem RETA (≈90°) → chanfro automático pós-SES: cada quina vira 2×45°
    (cateto pequeno, default 0,12mm) e o DRC que roda logo em seguida valida
    que o chanfro não aproximou cobre de nada.

Medição nos goldens antes da regra: Freerouting 2.5.0 emite 12–16 quinas
retas por placa (grade de roteamento) — por isso 90° é chanfro, não erro.

SEMÂNTICA DA VIRAGEM (bug do 1º detector, corrigido): viragem = 180° −
ângulo entre os vetores "away" (p → a OUTRA ponta de cada segmento). O 1º
detector media o ângulo cru entre as direções start→end, que depende da
ORIENTAÇÃO em que cada segmento foi escrito: dobra real de 45° com o 2º
fio invertido aparecia como "aguda 135°" e 2 fios chegando em lados
opostos do MESMO PAD apareciam como "aguda 180°" — 6–13 falsos positivos
por placa nos builds da matriz (28-10). Prova da fórmula: colinear →
aways opostos → ângulo 180° → viragem 0°; quina reta → aways a 90° →
viragem 90°; dobra 45° → aways a 135° → viragem 45°.

PADS E VIAS SÃO TERMINAIS (2º bug conceitual): ponto que coincide com pad
ou via não é quina — é CONEXÃO. Entrada reta/diagonal no pad é normal no
Freerouting; chanfrar ali cortaria o fio e DESCONECTARIA o terminal. Pad/
via ficam de fora do chanfro E do gate de agudos. Posições absolutas: pad
é relativo ao footprint (com rotação): abs = fp + (px·cosθ + py·sinθ,
−px·sinθ + py·cosθ) — frame Y-down, validado no jig O02 (90°: (x,y)→(y,−x)).
"""
from __future__ import annotations

import math
import re
import uuid
from pathlib import Path

_EPS = 0.01                 # coincidência de pontos (mm)
_FAIXA_RETA = (89.5, 90.5)  # viragem considerada "quina reta"
_CATETO = 0.12              # cateto do chanfro (mm); diagonal exata a 45°
_MIN_TRAMO = 0.06           # tramo mínimo remanescente (mm)

_RE_SEG = re.compile(
    r'\(segment\s*\(start ([\d.\-]+) ([\d.\-]+)\)\s*\(end ([\d.\-]+) ([\d.\-]+)\)'
    r'\s*\(width ([\d.]+)\)\s*\(layer "([^"]+)"\)\s*\(net "([^"]+)"\)'
    r'\s*\(uuid "([^"]+)"\)'
)
_RE_VIA = re.compile(r'\(via(?:\s+\w+)?\s*\(at ([\d.\-]+) ([\d.\-]+)\)')
_RE_AT = re.compile(r'\(at ([\d.\-]+) ([\d.\-]+)(?: ([\d.\-]+))?\)')


def _bloco(txt: str, i: int) -> tuple[int, int]:
    """Span [i, fim) do s-expr que começa em i (por profundidade de parênteses)."""
    prof = 0
    for j in range(i, len(txt)):
        if txt[j] == '(':
            prof += 1
        elif txt[j] == ')':
            prof -= 1
            if prof == 0:
                return i, j + 1
    return i, len(txt)


def _pads_e_vias(txt: str) -> set[tuple[float, float]]:
    """Posições ABSOLUTAS de pads (transform do footprint) e vias — terminais."""
    pts: set[tuple[float, float]] = set()
    for m in _RE_VIA.finditer(txt):
        pts.add((round(float(m.group(1)), 2), round(float(m.group(2)), 2)))
    for m in re.finditer(r'\(footprint\s', txt):
        ini, fim = _bloco(txt, m.start())
        blk = txt[ini:fim]
        # o (at ...) do footprint vem ANTES do 1º (pad / (fp_text (formato KiCad)
        cortes = [k for k in (blk.find('(pad '), blk.find('(fp_text ')) if k >= 0]
        corte = min(cortes) if cortes else len(blk)
        mf = _RE_AT.search(blk[:corte])
        if not mf:
            continue
        fx, fy = float(mf.group(1)), float(mf.group(2))
        teta = math.radians(float(mf.group(3)) if mf.group(3) else 0.0)
        c, s = math.cos(teta), math.sin(teta)
        for mp in re.finditer(r'\(pad\s', blk):
            pi, pf = _bloco(blk, mp.start())
            at = _RE_AT.search(blk[pi:pf])
            if not at:
                continue
            px, py = float(at.group(1)), float(at.group(2))
            # ARREDONDA NA ENTRADA: o transform de rotação gera floats tipo
            # 33.99289999999999 e a comparação com o ponto do fio (arredondada
            # em _e_terminal) nunca casava (bug NRST, 28-10)
            pts.add((round(fx + px * c + py * s, 2), round(fy - px * s + py * c, 2)))
    return pts


def _e_terminal(p: tuple, terminais: set[tuple[float, float]]) -> bool:
    """p coincide com algum pad/via (grade de 0,01mm com vizinhança ±_EPS)."""
    cx, cy = round(p[0], 2), round(p[1], 2)
    for dx in (-0.01, 0.0, 0.01):
        for dy in (-0.01, 0.0, 0.01):
            if (round(cx + dx, 2), round(cy + dy, 2)) in terminais:
                return True
    return False


def _viragem(a: dict, b: dict, p: tuple) -> float:
    """VIRAGEM real da trilha no ponto p (0° = segue reto, 45° = dobra,
    90° = quina reta, 135° = agudo/acid trap, 180° = retorno sobre si).

    away = vetor de p PARA a outra ponta do segmento; viragem = 180° −
    ângulo(away_A, away_B). Independente da orientação de escrita.
    """
    pa_a = abs(a['start'][0] - p[0]) < _EPS and abs(a['start'][1] - p[1]) < _EPS
    pb_b = abs(b['start'][0] - p[0]) < _EPS and abs(b['start'][1] - p[1]) < _EPS
    oa = a['end'] if pa_a else a['start']
    ob = b['end'] if pb_b else b['start']
    va = (oa[0] - p[0], oa[1] - p[1])
    vb = (ob[0] - p[0], ob[1] - p[1])
    m1 = math.hypot(*va)
    m2 = math.hypot(*vb)
    if m1 < _EPS or m2 < _EPS:
        return 0.0
    cos = (va[0] * vb[0] + va[1] * vb[1]) / (m1 * m2)
    return 180.0 - math.degrees(math.acos(max(-1.0, min(1.0, cos))))


def _seg_texto(start: tuple, end: tuple, larg: str, layer: str, net: str,
               uid: str, indent: str = '\t') -> str:
    return (f'(segment\n{indent}\t(start {start[0]:.6f} {start[1]:.6f})\n'
            f'{indent}\t(end {end[0]:.6f} {end[1]:.6f})\n{indent}\t(width {larg})\n'
            f'{indent}\t(layer "{layer}")\n{indent}\t(net "{net}")\n'
            f'{indent}\t(uuid "{uid}")\n{indent})\n')


def corrigir_angulos(pcb_path: Path, cateto: float = _CATETO) -> tuple[int, list[str]]:
    """Chanfra quinas retas (90°→2×45°) e devolve (n_chanfros, agudos).

    Agudos (interior <90°, FORA de pads/vias) NÃO são corrigidos — voltam
    na lista p/ o cli bloquear o export (regra de ouro §9: sem acid trap).
    """
    txt = pcb_path.read_text(encoding='utf-8')
    segs = []
    for m in _RE_SEG.finditer(txt):
        ini, fim = _bloco(txt, m.start())
        segs.append({
            'start': (float(m.group(1)), float(m.group(2))),
            'end': (float(m.group(3)), float(m.group(4))),
            'width': m.group(5), 'layer': m.group(6), 'net': m.group(7),
            'uuid': m.group(8), 'span': (ini, fim),
            'trim_start': 0.0, 'trim_end': 0.0,
        })
    if len(segs) < 2:
        return 0, []

    # terminais: pad/via não é quina (conexão) — nem chanfro, nem gate
    terminais = _pads_e_vias(txt)

    # junções agrupadas POR PONTO (mesma layer+net): 2 fios = possível quina;
    # 3+ fios = junção ESTRELA/T — conexão em ramificação do grid de 45° (a
    # cunha de 45° entre ramo e braço é topologia de junção, não quina de
    # trilha: universal em placas reais, aceita — bug I03/STM32 28-10)
    por_chave: dict[tuple, list[int]] = {}
    for k, s in enumerate(segs):
        por_chave.setdefault((s['layer'], s['net']), []).append(k)
    juncoes: dict[tuple, set[int]] = {}
    ptos: dict[tuple, tuple] = {}
    for idxs in por_chave.values():
        for ii in range(len(idxs)):
            for jj in range(ii + 1, len(idxs)):
                a, b = segs[idxs[ii]], segs[idxs[jj]]
                for pa in (a['start'], a['end']):
                    for pb in (b['start'], b['end']):
                        if abs(pa[0] - pb[0]) < _EPS and abs(pa[1] - pb[1]) < _EPS:
                            chave = (a['layer'], a['net'],
                                     round(pa[0], 3), round(pa[1], 3))
                            juncoes.setdefault(chave, set()).update((idxs[ii], idxs[jj]))
                            ptos[chave] = pa
    quinas: list[tuple[int, int, tuple, float]] = []   # (i, j, ponto, viragem)
    agudos: list[str] = []
    for chave, idxs in juncoes.items():
        p = ptos[chave]
        if _e_terminal(p, terminais):
            continue  # terminal: conexão, não quina
        if len(idxs) > 2:
            continue  # estrela/T: ramificação, não quina
        i, j = sorted(idxs)
        v = _viragem(segs[i], segs[j], p)
        if v > _FAIXA_RETA[1]:
            agudos.append(
                f"{segs[i]['net']}: quina aguda {v:.0f}° em "
                f"({p[0]:.2f}, {p[1]:.2f})")
        elif v >= _FAIXA_RETA[0]:
            quinas.append((i, j, p, v))
    if not quinas and not agudos:
        return 0, []

    # PASSO 1 — decide os trims por (segmento, extremidade) ANTES de mexer na
    # geometria: numa junção de 3+ segmentos, cada quina acumula trim na sua
    # própria extremidade e a diagonal usa o ponto FINAL (com trim total).
    trims: dict[tuple[int, str], float] = {}
    pares_diag: list[tuple[int, str, int, str]] = []
    n_chanfros = 0
    for i, j, ponto, _v in quinas:
        la = _lado(segs[i], ponto)
        lb = _lado(segs[j], ponto)
        disp_a = _disponivel(segs[i]) - trims.get((i, la), 0.0)
        disp_b = _disponivel(segs[j]) - trims.get((j, lb), 0.0)
        d = min(cateto, disp_a, disp_b)
        if d < 0.04:
            continue  # tramo curto demais p/ chanfrar sem degenerar
        trims[(i, la)] = trims.get((i, la), 0.0) + d
        trims[(j, lb)] = trims.get((j, lb), 0.0) + d
        pares_diag.append((i, la, j, lb))
        n_chanfros += 1
    if n_chanfros == 0:
        return 0, agudos

    def ponto_final(idx: int, lado: str) -> tuple[float, float]:
        s = segs[idx]
        d = trims.get((idx, lado), 0.0)
        if d <= 0:
            return s['end'] if lado == 'trim_end' else s['start']
        return _recolher(s, lado, d)

    # PASSO 2 — diagonais com a geometria FINAL (exatas a 45° quando os dois
    # catetos são iguais; nunca geram agudo — viragens somam 90°)
    diaginas: list[str] = []
    for i, la, j, lb in pares_diag:
        diaginas.append(_seg_texto(ponto_final(i, la), ponto_final(j, lb),
                                   segs[i]['width'], segs[i]['layer'],
                                   segs[i]['net'], str(uuid.uuid4())))

    # reconstrução: substituições de TRÁS pra FRENTE (spans de trás continuam
    # válidos); ponto de inserção das diagonais = FIM do último bloco trocado.
    # Cada substituição ANTERIOR a ela desloca o ponto em len(novo)−len(velho).
    # sincroniza trims na geometria (partes usa esses campos)
    for (idx, lado), d in trims.items():
        segs[idx][lado] = d
    partes: list[tuple[int, int, str]] = []
    for s in segs:
        if s['trim_start'] > 0 or s['trim_end'] > 0:
            ns = _recolher(s, 'trim_start', s['trim_start']) if s['trim_start'] > 0 else s['start']
            ne = _recolher(s, 'trim_end', s['trim_end']) if s['trim_end'] > 0 else s['end']
            partes.append((s['span'][0], s['span'][1],
                           _seg_texto(ns, ne, s['width'], s['layer'], s['net'], s['uuid'])))
    ini_ultimo = max(ini for ini, _, _ in partes)
    inserir_em: int | None = None
    for ini, fim, novo in sorted(partes, key=lambda p: p[0], reverse=True):
        if ini == ini_ultimo:
            inserir_em = ini + len(novo)
        else:
            inserir_em += len(novo) - (fim - ini)
        txt = txt[:ini] + novo + txt[fim:]
    if inserir_em is not None:
        txt = txt[:inserir_em] + ''.join(diaginas) + txt[inserir_em:]
    pcb_path.write_text(txt, encoding='utf-8')
    return n_chanfros, agudos


def _lado(seg: dict, ponto: tuple) -> str:
    """Qual extremidade do segmento toca o ponto (trim_start ou trim_end)."""
    if (abs(seg['end'][0] - ponto[0]) < _EPS and abs(seg['end'][1] - ponto[1]) < _EPS):
        return 'trim_end'
    return 'trim_start'


def _disponivel(seg: dict) -> float:
    """Comprimento do segmento menos trims já marcados, menos o tramo mínimo."""
    comp = math.hypot(seg['end'][0] - seg['start'][0], seg['end'][1] - seg['start'][1])
    return comp - seg['trim_start'] - seg['trim_end'] - _MIN_TRAMO


def _recolher(seg: dict, lado: str, d: float) -> tuple[float, float]:
    """Ponto da extremidade `lado` recolhido d para dentro do segmento."""
    sx, sy = seg['start']
    ex, ey = seg['end']
    comp = math.hypot(ex - sx, ey - sy)
    if comp < _EPS:
        return seg['start'] if lado == 'trim_start' else seg['end']
    ux, uy = (ex - sx) / comp, (ey - sy) / comp
    if lado == 'trim_end':
        return (ex - ux * d, ey - uy * d)
    return (sx + ux * d, sy + uy * d)

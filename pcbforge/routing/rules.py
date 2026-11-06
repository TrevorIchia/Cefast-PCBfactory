"""routing.rules — regras do ROUTEADOR no DSN (pós-processamento de texto).

Diretriz do usuário (28-10-2026): "trilhas passando muito perto dos pads sem
necessidade" + "entorno de ilhas e pads como área de restrição" + "a
espessura pode ser maior, depende da corrente".

Fundamentação (pesquisa 28-10-2026):
  - JLCPCB (capacidades oficiais): pad→trilha MÍNIMO 0,20mm — "more whenever
    possible"; AllPCB: "design with a safety margin beyond the minimum";
    Auckland/Altium: 0,5mm geral. O router encosta no mínimo SEMPRE QUE PODE
    — então damos a ele um clearance de roteamento MAIOR que o mínimo de
    fabricação (que segue no DRC como gate).
  - Issue #558 do Freerouting: o DSN não carrega clearance cobre→borda — o
    clearance maior do roteador também é a nossa margem na borda.
  - Largura por corrente (B2): NXP AN3962 1mm/A (conservador); JLCPCB
    "15+ mil para power". Só nets declaradas (perfil high_current_traces,
    com fallback p/ rails com corrente ≥0,3A) recebem classe própria com
    width; o resto fica na kicad_default.

Formato DSN (provas no lm358): `(rule (width 250) (clearance 250) (clearance
62.5 (type smd_smd)))` no structure + `(class kicad_default <nets...> (rule
(width 250) (clearance 250)))` no network. Unidade: 1000 = 1,0mm (resolução
10µm). O `(clearance N (type ...))` tipado NUNCA é tocado.
"""
from __future__ import annotations

import re
from pathlib import Path

_RE_CLEARANCE_PELADO = re.compile(r'\(clearance (\d+(?:\.\d+)?)\)')
_RE_CLASS = re.compile(r'\(class\s+([^\n(]+)\n')
_RE_USE_VIA = re.compile(r'\(use_via "([^"]+)"\)')
_A_FALLBACK_RAILS = 0.3  # A — corrente que merece classe de largura própria


def clearance_roteador(perfil: dict) -> float:
    """Clearance que o ROUTEADOR obedece (≠ mínimo de fabricação, que fica no DRC)."""
    base = float(perfil.get('min_clearance_mm', 0.25))
    return float(perfil.get('clearance_roteador_mm', round(base + 0.05, 3)))


def largura_por_corrente(corrente_a: float, min_trace_mm: float) -> float:
    """NXP AN3962 (conservador): 1mm por ampere; piso = min_trace do perfil."""
    return round(max(float(min_trace_mm), float(corrente_a)), 3)


def nets_de_corrente(perfil: dict, netlist: dict) -> dict[str, float]:
    """{net: corrente_A} — perfil high_current_traces; fallback: rails ≥0,3A."""
    saida: dict[str, float] = {}
    for hc in (perfil.get('high_current_traces') or []):
        net = hc.get('net')
        a = float(hc.get('A', 0) or 0)
        if net and a > 0:
            saida[net] = max(saida.get(net, 0.0), a)
    if not saida:
        for rail in (netlist.get('rails') or []):
            a = float(rail.get('current', 0) or 0)
            if a >= _A_FALLBACK_RAILS and rail.get('net'):
                saida[rail['net']] = max(saida.get(rail['net'], 0.0), a)
    return saida


def _tira_das_classes(txt: str, removidas: set[str]) -> str:
    """Retira as nets em `removidas` de TODOS os (class ...) do DSN.

    Bloco balanceado: `(class <nome> <nets multilinha> <escopos>)`. Devolve
    o texto com as class-header renascidas (nets em linha única).
    """
    saida: list[str] = []
    i = 0
    trocas = 0
    while True:
        j = txt.find('(class', i)
        if j < 0:
            saida.append(txt[i:])
            break
        fim, prof = j, 0
        k = j
        while k < len(txt):
            c = txt[k]
            if c == '(':
                prof += 1
            elif c == ')':
                prof -= 1
                if prof == 0:
                    fim = k
                    break
            k += 1
        bloco = txt[j:fim + 1]
        m = re.search(r'\(', bloco[len('(class'):])
        header = bloco[len('(class'):len('(class') +
                       (m.start() if m else len(bloco) - len('(class'))]
        toks = header.split()
        if len(toks) < 2:  # class sem nets — não mexe
            saida.append(txt[i:fim + 1])
            i = fim + 1
            continue
        nome, nets = toks[0], toks[1:]
        nets_f = [t for t in nets if t.strip('"') not in removidas]
        if not nets_f:
            # class esvaziada: descarta o bloco INTEIRO (Specctra: class
            # 0 nets é lixo — e Freerouting pode largar as regras do resto)
            trocas += 1
            saida.append(txt[i:j])
        elif nets_f != nets:
            trocas += 1
            cab = f' {nome} ' + ' '.join(nets_f) + '\n'
            corpo = bloco[len('(class') + len(header):]
            saida.append(txt[i:j] + '(class' + cab + corpo)
        else:
            saida.append(txt[i:fim + 1])
        i = fim + 1
    return ''.join(saida)


def aplicar(dsn_path: Path, perfil: dict, netlist: dict, log: list[str]) -> None:
    """Grava no DSN: clearance do roteador + classes de largura por corrente."""
    txt = dsn_path.read_text(encoding='utf-8')

    clear_mm = clearance_roteador(perfil)
    unidades = int(round(clear_mm * 1000))
    txt, n = _RE_CLEARANCE_PELADO.subn(f'(clearance {unidades})', txt)
    if n == 0:
        log.append(f'regras do roteador: nenhum (clearance N) pelado no DSN — nada trocado')
    clear_min = float(perfil.get('min_clearance_mm', 0.25))

    min_trace = float(perfil.get('min_trace_mm', 0.25))
    grupos: dict[float, list[str]] = {}
    for net, a in nets_de_corrente(perfil, netlist).items():
        grupos.setdefault(largura_por_corrente(a, min_trace), []).append(net)

    if grupos:
        via = _RE_USE_VIA.search(txt)
        via_txt = via.group(1) if via else 'Via[0-1]_500:300_um'
        # tira as nets de potência das classes existentes (1 net = 1 classe no
        # Specctra). A lista de nets do class é MULTILINHA — parser por bloco
        # balanceado, NUNCA regex de linha (prova 05-11: GND/BAT-/VPROT
        # ficavam duplicados e Freerouting descartava a classe → nets de
        # power sem fio nenhum no SES com "0 unrouted" mentiroso).
        grupos_direto = {n for nets in grupos.values() for n in nets}
        txt = _tira_das_classes(txt, grupos_direto)

        blocos = []
        for larg_mm, nets in sorted(grupos.items()):
            nome = f'potencia_{int(round(larg_mm * 1000))}'
            nets_txt = ' '.join(nets)
            blocos.append(
                f'    (class {nome} {nets_txt}\n'
                f'      (circuit\n        (use_via "{via_txt}")\n      )\n'
                f'      (rule\n        (width {int(round(larg_mm * 1000))})\n'
                f'        (clearance {unidades})\n      )\n    )\n')
        i = txt.find('(class')
        if i >= 0:
            txt = txt[:i] + ''.join(blocos) + txt[i:]
        larguras_txt = ', '.join(
            f"{'+'.join(nets)} {larg_mm}mm" for larg_mm, nets in sorted(grupos.items()))
        log.append(f'regras do roteador: clearance {clear_mm}mm (entorno de pads/ilhas; '
                   f'mín fabricação {clear_min}mm fica no DRC); largura por corrente (B2, '
                   f'NXP 1mm/A): {larguras_txt}')
    else:
        log.append(f'regras do roteador: clearance {clear_mm}mm (entorno de pads/ilhas; '
                   f'mín fabricação {clear_min}mm fica no DRC); sem nets de corrente '
                   'declaradas — larguras ficam no mínimo do perfil')

    dsn_path.write_text(txt, encoding='utf-8')

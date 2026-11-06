# Testes B1 (regra de ângulos, pesquisa 28-10-2026): quinas retas (90°)
# são CHANFRADAS pós-SES em 2×45°; ângulos AGUDOS (<90° interior) são
# bloqueadores — nunca exportar (acid trap: NextPCB/Altium/e-e).
#
# Semântica da viragem (bug do 1º detector corrigido): viragem = 180° −
# ângulo entre vetores "away" (p → outra ponta). O helper _viragens aqui
# usa essa MESMA convenção (45/90 reais) e é independente do módulo.
# Casos regressão dos falsos positivos dos builds 28-10:
#   - dobra 45° com 2º fio invertido → antigo via "aguda 135°";
#   - 2 fios em lados opostos do mesmo pad → antigo via "aguda 180°";
#   - quina em pad/via → antigo chanifraria e DESCONECTARIA o terminal.

from __future__ import annotations

import math
import re

from pcbforge.routing.angulos import corrigir_angulos

_PAD_EM_2_0 = '''\t(footprint "Test:FP"
\t\t(at 2.0 0.0 0)
\t\t(pad "1" smd rect
\t\t\t(at 0 0)
\t\t\t(size 1 1)
\t\t\t(layer "F.Cu")
\t\t)
\t)
'''

_VIA_EM_2_0 = '''\t(via
\t\t(at 2.0 0.0)
\t\t(size 0.6)
\t\t(drill 0.3)
\t\t(layers "F.Cu" "B.Cu")
\t\t(net "S1")
\t)
'''


def _pcb(segs: list[tuple[float, float, float, float, str]], extra: str = "") -> str:
    """kicad_pcb mínimo com segments (net por NOME, formato KiCad 10)."""
    blocos = []
    for x1, y1, x2, y2, net in segs:
        blocos.append(
            f'\t(segment\n\t\t(start {x1} {y1})\n\t\t(end {x2} {y2})\n'
            f'\t\t(width 0.25)\n\t\t(layer "F.Cu")\n\t\t(net "{net}")\n'
            f'\t\t(uuid "00000000-0000-0000-0000-{len(blocos):012d}")\n\t)\n')
    return '(kicad_pcb\n' + ''.join(blocos) + extra + ')\n'


def _segmentos(txt: str):
    out = []
    for m in re.finditer(r'\(segment\s*\(start ([\d.\-]+) ([\d.\-]+)\)\s*'
                         r'\(end ([\d.\-]+) ([\d.\-]+)\)\s*\(width ([\d.]+)\)\s*'
                         r'\(layer "([^"]+)"\)\s*\(net "([^"]+)"\)', txt):
        out.append(tuple(float(m.group(i)) for i in (1, 2, 3, 4)) + (m.group(6),))
    return out


def _viragens(segs):
    """Viragens REAIS entre pares encostados (mesma net), via vetores away."""
    v = []
    for i, a in enumerate(segs):
        for b in segs[i + 1:]:
            ends_a = {(round(a[0], 3), round(a[1], 3)), (round(a[2], 3), round(a[3], 3))}
            ends_b = {(round(b[0], 3), round(b[1], 3)), (round(b[2], 3), round(b[3], 3))}
            comum = ends_a & ends_b
            if not comum:
                continue
            p = comum.pop()
            oa = (a[2], a[3]) if (round(a[0], 3), round(a[1], 3)) == p else (a[0], a[1])
            ob = (b[2], b[3]) if (round(b[0], 3), round(b[1], 3)) == p else (b[0], b[1])
            va = (oa[0] - p[0], oa[1] - p[1])
            vb = (ob[0] - p[0], ob[1] - p[1])
            cos = (va[0] * vb[0] + va[1] * vb[1]) / (math.hypot(*va) * math.hypot(*vb))
            v.append(round(180.0 - math.degrees(math.acos(max(-1, min(1, cos))))))
    return v


def test_B1_quina_reta_vira_2x45(tmp_path):
    p = tmp_path / "t.kicad_pcb"
    p.write_text(_pcb([(0.0, 0.0, 2.0, 0.0, "VCC"),   # horizontal
                       (2.0, 0.0, 2.0, 2.0, "VCC")]))  # vertical → quina 90°
    n, agudos = corrigir_angulos(p)
    assert n == 1 and not agudos
    segs = _segmentos(p.read_text())
    assert len(segs) == 3, "2 tramos chanfrados + 1 diagonal"
    vs = sorted(_viragens(segs))
    assert vs == [45, 45], f"esperava duas viragens de 45°, veio {vs}"


def test_B1_agudo_bloqueia(tmp_path):
    p = tmp_path / "t.kicad_pcb"
    # viragem de 135° = interior de 45° (agudo, acid trap): o 2º tramo VOLTA
    p.write_text(_pcb([(0.0, 0.0, 2.0, 0.0, "VCC"),
                       (2.0, 0.0, 1.0, -1.0, "VCC")]))
    n, agudos = corrigir_angulos(p)
    assert n == 0 and len(agudos) == 1
    assert "VCC" in agudos[0]


def test_B1_dobra45_com_fio_invertido_nao_e_agudo(tmp_path):
    """Regressão do falso 'aguda 135°' dos builds 28-10: dobra real de 45°
    com o 2º segmento escrito ao contrário (a ponta comum é o END dele).
    O detector antigo media o ângulo cru entre direções start→end."""
    p = tmp_path / "t.kicad_pcb"
    p.write_text(_pcb([(0.0, 0.0, 2.0, 0.0, "VCC"),   # chega no ponto indo →
                       (3.0, 1.0, 2.0, 0.0, "VCC")]))  # escrito de trás pra frente
    n, agudos = corrigir_angulos(p)
    assert n == 0 and not agudos, f"falso agudo: {agudos}"
    assert _viragens(_segmentos(p.read_text())) == [45]  # dobra 45° permitida


def test_B1_fios_opostos_no_mesmo_pad_nao_e_agudo(tmp_path):
    """Regressão do falso 'aguda 180°' dos builds 28-10: 2 fios chegando em
    lados OPOSTOS do MESMO pad (junção estrela — passagem reta pelo pad)."""
    p = tmp_path / "t.kicad_pcb"
    p.write_text(_pcb([(0.0, 0.0, 2.0, 0.0, "GND"),
                       (4.0, 0.0, 2.0, 0.0, "GND")], extra=_PAD_EM_2_0))
    n, agudos = corrigir_angulos(p)
    assert n == 0 and not agudos, f"falso agudo: {agudos}"


def test_B1_quina_em_pad_nao_chanfra(tmp_path):
    """Pad é TERMINAL: quina em pad não vira chanfro (o trim cortaria o fio
    e desconectaria o pad)."""
    p = tmp_path / "t.kicad_pcb"
    p.write_text(_pcb([(0.0, 0.0, 2.0, 0.0, "S1"),    # entra no pad por cima
                       (2.0, 2.0, 2.0, 0.0, "S1")], extra=_PAD_EM_2_0))
    n, agudos = corrigir_angulos(p)
    assert n == 0 and not agudos
    assert len(_segmentos(p.read_text())) == 2, "ninguém foi cortado"


def test_B1_quina_em_via_nao_chanfra(tmp_path):
    """Via é terminal igual a pad: quina na via é conexão, não quina."""
    p = tmp_path / "t.kicad_pcb"
    p.write_text(_pcb([(0.0, 0.0, 2.0, 0.0, "S1"),
                       (2.0, 2.0, 2.0, 0.0, "S1")], extra=_VIA_EM_2_0))
    n, agudos = corrigir_angulos(p)
    assert n == 0 and not agudos
    assert len(_segmentos(p.read_text())) == 2


def test_B1_agudo_em_pad_nao_bloqueia(tmp_path):
    """Entrada diagonal aguda NO pad é normal no Freerouting (solda/máscara
    cobrem a cunha) — não é acid trap de trilha."""
    p = tmp_path / "t.kicad_pcb"
    # viragem real 135° no pad (2.0, 0.0): aways a 45°
    p.write_text(_pcb([(0.0, 0.0, 2.0, 0.0, "S1"),
                       (2.7, -0.7, 2.0, 0.0, "S1")], extra=_PAD_EM_2_0))
    n, agudos = corrigir_angulos(p)
    assert n == 0 and not agudos


def test_B1_placa_verde_gera_so_chanfros(tmp_path):
    """Caso real medido: Freerouting emite 45° e 90° — nunca agudo. O
    corrigidor tem de chanfrar TODAS as quinas retas e reportar 0 agudos."""
    segs = [(0.0, 0.0, 4.0, 0.0, "GND"),
            (4.0, 0.0, 4.0, 4.0, "GND"),
            (4.0, 4.0, 6.0, 4.0, "GND"),
            (6.0, 4.0, 6.0, 6.0, "GND")]
    p = tmp_path / "t.kicad_pcb"
    p.write_text(_pcb(segs))
    n, agudos = corrigir_angulos(p)
    assert n == 3 and not agudos  # escada: 3 dobras retas
    txt = p.read_text()
    vs = sorted(_viragens(_segmentos(txt)))
    assert vs == [45] * 6, f"viragens pós-chanfro: {vs}"
    # nenhuma quebra de continuidade: cada ponto comum une exatamente 2 tramos
    segs_novos = _segmentos(txt)
    pontos: dict[tuple, int] = {}
    for s in segs_novos:
        for pto in ((round(s[0], 3), round(s[1], 3)), (round(s[2], 3), round(s[3], 3))):
            pontos[pto] = pontos.get(pto, 0) + 1
    assert all(c == 2 for p, c in pontos.items() if p not in {(0.0, 0.0), (6.0, 6.0)}) \
        and pontos[(0.0, 0.0)] == 1 and pontos[(6.0, 6.0)] == 1, \
        f"encadeamento quebrou: {pontos}"  # pontas da cadeia têm 1; juntas, 2


def test_B1_colinear_nao_mexe(tmp_path):
    """Tramos colineares encostados (viragem 0°) não viram chanfro — só
    viragens na faixa 89,5–90,5°."""
    p = tmp_path / "t.kicad_pcb"
    p.write_text(_pcb([(0.0, 0.0, 2.0, 0.0, "VCC"),
                       (2.0, 0.0, 4.0, 0.0, "VCC")]))  # colinear
    n, agudos = corrigir_angulos(p)
    assert n == 0 and not agudos
    assert len(_segmentos(p.read_text())) == 2


_PAD_GIRADO_90 = '''\t(footprint "Test:FPg"
\t\t(at 2.0 -0.975 90)
\t\t(pad "1" smd rect
\t\t\t(at -0.975 0)
\t\t\t(size 1.5 0.6)
\t\t\t(layer "F.Cu")
\t\t)
\t)
'''


def test_B1_pad_em_footprint_girado_90_e_terminal(tmp_path):
    """Regressão NRST (STM32, 28-10): pad de footprint com ROTAÇÃO 90° — o
    abs com transform tem de bater com o ponto do fio, e o float da
    transformação (tipo 33.9928999999) não pode quebrar a comparação de
    terminal."""
    p = tmp_path / "t.kicad_pcb"
    # quina em L exatamente no pad (2.0, 0.0) — terminal: sem chanfro
    p.write_text(_pcb([(0.0, 0.0, 2.0, 0.0, "S1"),
                       (2.0, 2.0, 2.0, 0.0, "S1")], extra=_PAD_GIRADO_90))
    n, agudos = corrigir_angulos(p)
    assert n == 0 and not agudos
    assert len(_segmentos(p.read_text())) == 2, "ninguém foi cortado"


def test_B1_estrela_3raios_com_ramificacao_45_aceita(tmp_path):
    """Regressão do 'aguda 135°' do I03/STM32 (28-10): diagonal reta
    passando pelo ponto + ramificação — junção em T/estrela, não quina (a
    cunha de 45° entre ramo e braço é topologia de CONEXÃO, universal em
    placas reais; o gate protege quina de trilha)."""
    p = tmp_path / "t.kicad_pcb"
    p.write_text(_pcb([(51.0, 27.0, 52.34, 26.32, "GND"),      # diagonal chegando
                       (52.34, 26.32, 52.49, 26.17, "GND"),   # diagonal colinear saindo
                       (52.34, 26.32, 57.25, 26.32, "GND")]))  # ramo horizontal
    n, agudos = corrigir_angulos(p)
    assert n == 0 and not agudos, f"falso agudo: {agudos}"


def test_B1_diagonal_45_exata(tmp_path):
    """A diagonal do chanfro tem de ser exatamente a 45° (mesmo cateto dos
    dois lados) — direção (±d, ±d)."""
    p = tmp_path / "t.kicad_pcb"
    p.write_text(_pcb([(0.0, 0.0, 2.0, 0.0, "S1"),
                       (2.0, 0.0, 2.0, 2.0, "S1")]))
    corrigir_angulos(p)
    # diagonal = o único segmento com deslocamento em X E em Y
    diag = [s for s in _segmentos(p.read_text())
            if abs(s[2] - s[0]) > 1e-9 and abs(s[3] - s[1]) > 1e-9]
    assert len(diag) == 1
    d = diag[0]
    assert abs(abs(d[2] - d[0]) - abs(d[3] - d[1])) < 1e-6, \
        f"diagonal não é 45°: {d}"

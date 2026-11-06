# Testes F8 — componente "fixo": true no netlist (pré-requisito da regra A3:
# conector ancorado na borda com entrada de fio pra fora). O otimizador NÃO
# pode trocar, girar nem mover um componente fixado — em nenhuma seed.

from __future__ import annotations

import json
from pathlib import Path

from pcbforge.core import placement as pl

EXEMPLO_TI = Path(__file__).resolve().parents[2] / "examples" / "ex-attiny-isp-1l" / "netlist.json"

PERFIL = {"size_mm": {"w": 80, "h": 50}}


def _com_j2_fixo() -> dict:
    nl = json.loads(EXEMPLO_TI.read_text())
    j2 = next(c for c in nl["components"] if c["ref"] == "J2")
    j2["fixo"] = True
    j2["pos_mm"] = [47.0, 4.0]
    return nl


def test_F8_fixo_ancora_em_todas_as_seeds():
    nl = _com_j2_fixo()
    for seed in (1, 8, 9, 11):
        layout = pl.otimizar(nl, PERFIL, seed=seed, iteracoes=600)[0]
        assert layout["J2"][:2] == (47.0, 4.0), \
            f"seed {seed}: J2 fixo foi movido p/ {layout['J2'][:2]}"


def test_F8_fixo_nao_bloqueia_o_resto():
    """O J2 fixo tem de continuar ancorado MESMO quando o annealing move os
    outros componentes — e os demais seguem livres (dentro da margem)."""
    nl = _com_j2_fixo()
    layout = pl.otimizar(nl, PERFIL, seed=8, iteracoes=600)[0]
    assert layout["J2"][:2] == (47.0, 4.0)
    outros = [v for r, v in layout.items() if r != "J2"]
    assert any(v[:2] != (47.0, 4.0) for v in outros)
    for v in outros:
        assert 4.0 <= v[0] <= 76.0 and 4.0 <= v[1] <= 46.0, f"{v} fora da margem"


def test_F8_clamp_borda_nao_move_fixo():
    """Regressão sanduíche (28-10): bornier com courtyard ±3mm ancorado na
    borda — o _clamp_borda empurrava o FIXO pra dentro da folga (J1
    4.0→5.045, J2 56.0→53.635) e rompia o contrato da âncora em silêncio.
    A âncora que cruza a margem É o design (entrada de fio pra fora, A7)."""
    nl = {"components": [
        {"ref": "J1", "value": "MKDS", "type": "conector",
         "footprint_ref": "TerminalBlock_Phoenix:"
                          "TerminalBlock_Phoenix_MKDS-1,5-2_1x02_P5.00mm_Horizontal",
         "fixo": True, "pos_mm": [4.0, 26.0]},
    ], "connections": []}
    pos_inicial = {"J1": (4.0, 26.0, 0)}
    saida = pl._clamp_borda(nl, pos_inicial, 60.0, 40.0)
    assert saida["J1"][:2] == (4.0, 26.0), \
        f"clamp moveu o fixo: {saida['J1'][:2]}"


def test_G04_furos_sao_keepout_no_placement():
    """Regressão sanduíche (28-10, DRC courtyards_overlap H1xR1): furos M3
    são adicionados SÓ no gerador — o placement não os via. Agora são
    keepout: componente móvel com courtyard sobre o furo é desencalhado."""
    nl = {"components": [
        {"ref": "J1", "value": "HDR", "type": "conector",
         "footprint_ref": "Connector_PinHeader_2.54mm:PinHeader_2x03_P2.54mm_Vertical",
         "fixo": True, "pos_mm": [30.0, 20.0]},
        {"ref": "R1", "value": "R", "type": "resistor",
         "footprint_ref": "Resistor_SMD:R_0603_1608Metric",
         "pos_mm": [3.0, 3.0]},  # em cima do furo H1 (3,3)
    ], "connections": []}
    perfil = {"size_mm": {"w": 60, "h": 40},
              "mounting": {"diameter_mm": 3.2, "corners": 4, "margin": 3}}
    furos = pl._caixas_furos(perfil)
    assert len(furos) == 4, "4 cantos ⇒ 4 furos"
    h1 = furos[0]
    assert abs(h1[0] - (3.0 - 3.492)) < 0.05 and abs(h1[2] - (3.0 + 3.495)) < 0.05, \
        f"bbox do courtyard do M3 (±3.49mm) ao redor do canto (3,3): {h1}"
    layout, _, _ = pl.otimizar(nl, perfil, seed=8)
    _, caixas = pl.coords_pads(nl, layout)
    for ref, b in caixas.items():
        if ref == "R1":  # móvel: tem de ter sido desencalhado de TODOS os furos
            for f in furos:
                overlap = b[0] < f[2] and f[0] < b[2] and b[1] < f[3] and f[1] < b[3]
                assert not overlap, f"{ref} continua sobre o furo: {b} x {f}"
    assert layout["J1"][:2] == (30.0, 20.0), "fixo intacto"


def test_F8_sem_fixo_otimizador_livre():
    """Regressão: sem a flag, comportamento de antes (J2 pode ser movido)."""
    nl = json.loads(EXEMPLO_TI.read_text())
    layout = pl.otimizar(nl, PERFIL, seed=8, iteracoes=600)[0]
    assert 4.0 <= layout["J2"][0] <= 76.0 and 4.0 <= layout["J2"][1] <= 46.0


def test_F8_fixo_sobrevive_a_sobreposicao():
    """No passe final de conflitos, o desencalhe só pode mover NÃO-fixos:
    o J2 ancorado continua em pos_mm mesmo se alguém sobrepor a caixa dele."""
    nl = _com_j2_fixo()
    for seed in range(1, 8):
        layout = pl.otimizar(nl, PERFIL, seed=seed, iteracoes=600)[0]
        assert layout["J2"][:2] == (47.0, 4.0), f"seed {seed}: J2 saiu do lugar"

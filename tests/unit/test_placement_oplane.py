# Testes O-plane da F2 — otimizador (Plano Mestre §17 F2): O01–O04
# Base: propriedades provadas no golden I03 (ATtiny, 11 comps, 12 nets).

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pcbforge.core import placement as pl

EXEMPLO_TI = Path(__file__).resolve().parents[2] / "examples" / "ex-attiny-isp-1l" / "netlist.json"

PERFIL = {"size_mm": {"w": 80, "h": 50}}


@pytest.fixture(scope="module")
def netlist():
    return json.loads(EXEMPLO_TI.read_text())


def test_O01_mst_monotonico(netlist):
    """O01: comprimento pós-otimização NUNCA acima do inicial, em qualquer seed."""
    for seed in (1, 3, 5, 7, 11):
        antes, depois = pl.otimizar(netlist, PERFIL, seed=seed, iteracoes=200)[1:]
        assert depois <= antes + 1e-6, f"seed {seed}: MST cresceu ({antes} → {depois})"


def test_I14_desencalhe_keepout_zero_conflitos():
    """F14c: courtyards presos dentro de um keepout grande (espírito do caso
    real do semaforo — court ESP32-WROOM-32 = 48×41 mm de zona de antena).
    O passe determinístico TEM que terminar com 0 sobreposição (nunca aceita piora).
    """
    nl = {
        "components": [
            {"ref": "U1", "type": "ci", "value": "esp32",
             "footprint_ref": "RF_Module:ESP32-WROOM-32", "pins": []},
            {"ref": "U2", "type": "ci", "value": "ams1117-3.3",
             "footprint_ref": "Package_TO_SOT_SMD:SOT-223", "pins": []},
            {"ref": "J1", "type": "conector", "value": "borne 2",
             "footprint_ref":
             "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2_1x02_P5.00mm_Horizontal",
             "pins": []},
        ],
        "connections": [], "rails": []}
    w, h = 95.0, 80.0
    # court ESP32 relativo (−30.8..+10.6 em Y): y0≥32 p/ court entrar na placa;
    # U2 e J1 SEM INTROBOS DENTRO do court (ॳ keepout de antena)
    melhor = {"U1": (48.0, 34.0, 0), "U2": (55.0, 30.0, 0), "J1": (65.0, 38.0, 0)}
    fixos: set[str] = set()
    saida = pl._desencalhe_caixas(nl, melhor, w, h, fixos)
    _, caixas = pl.coords_pads(nl, saida)
    assert pl.contar_conflitos(caixas) == 0
    for ref in melhor:
        assert ref in caixas          # nenhum componente perdido faz pass


def test_O02_giro_pads_jig(netlist):
    """O02: rotação gira os PADs com a fórmula validada pelo jig na F0.

    Frame do arquivo (Y p/ baixo), ang=90 ⇒ (x, y) → (y, −x).
    """
    assert pl._rot((3.0, 1.0, 10.0), 90) == (1.0, -3.0, 10.0)
    assert pl._rot((3.0, 1.0, 10.0), 180) == (-3.0, -1.0, 10.0)
    assert pl._rot((3.0, 1.0, 10.0), 270) == (-1.0, 3.0, 10.0)
    # coords_pads gira os pads de verdade: pin do U1 deve mudar de lado
    layout = pl.otimizar(netlist, PERFIL, seed=5, iteracoes=100)[0]
    pads0, _ = pl.coords_pads(netlist, {k: (v[0], v[1], 0) for k, v in layout.items()})
    padsR, _ = pl.coords_pads(netlist, layout)
    girou = any(pads0[u][p] != padsR[u][p] for u in pads0 for p in pads0[u])
    assert girou or all(v[2] == 0 for v in layout.values())


def test_O03_sem_sobreposicao_em_nenhuma_seed(netlist):
    """O03: as seeds verdes do golden (5/7) têm 0 sobreposições; seeds com
    mínimo local conflictivo (ex.: 3) existem e são REJEITADAS pela política
    do build (assert/loop de tentativa — F0), nunca aceitas."""
    for seed in (5, 7):
        layout = pl.otimizar(netlist, PERFIL, seed=seed, iteracoes=600)[0]
        confl = pl.contar_conflitos(pl.coords_pads(netlist, layout)[1])
        assert confl == 0, f"seed verde {seed} não pode ter sobreposição"

    congeladas = [s for s in range(1, 8)
                  if pl.contar_conflitos(pl.coords_pads(
                      netlist, pl.otimizar(netlist, PERFIL, seed=s, iteracoes=600)[0])[1])]
    # pelo menos UMA seed do golden tem de ser verde (o build termina OK)
    assert 5 in congeladas or len(congeladas) < 7, "nenhuma seed verde"


def test_O04_cruzamento_penalty_e_planario(netlist):
    """O04: cruzamentos contados; seed verde do golden é planária; custo determinístico."""
    layout = pl.otimizar(netlist, PERFIL, seed=5, iteracoes=600)[0]
    assert pl.contar_cruzamentos(netlist, layout) == 0, \
        "seed verde do golden deve ser planária (0 cruzamentos)"
    custo = pl.custo_total(netlist, layout, 80, 50)
    assert abs(custo - pl.custo_total(netlist, layout, 80, 50)) < 1e-6

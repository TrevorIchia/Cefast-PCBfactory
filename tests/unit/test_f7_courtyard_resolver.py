# Testes F7 — fechamento v1: courtyard via pcbnew (fonte = parser do DRC),
# resolver THT/ci (golden I04 NE555), clamp de borda do placement.

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pcbforge import paths
from pcbforge.core import placement as pl
from pcbforge.parts import resolve

EXEMPLO_TI = Path(__file__).resolve().parents[2] / "examples" / "ex-attiny-isp-1l" / "netlist.json"

DIP8 = "Package_DIP:DIP-8_W7.62mm"
J2 = "Connector_PinHeader_2.54mm:PinHeader_2x03_P2.54mm_Vertical"


# ---------- courtyard via pcbnew (F7) ----------

@pytest.mark.skipif(paths.ki_python() is None, reason="python do KiCad indisponível")
def test_F7_courtyard_pcbnew_dip8():
    via = pl.courtyards_via_pcbnew([DIP8])
    assert DIP8 in via, "DIP-8 tem courtyard real no .kicad_mod"
    x1, y1, x2, y2 = via[DIP8]
    assert (x2 - x1) > 9.5 and (y2 - y1) > 10.0     # prova ao vivo: 9,82×10,75


@pytest.mark.skipif(paths.ki_python() is None, reason="python do KiCad indisponível")
def test_F7_courtyard_j2_caso_do_falso_negativo():
    """J2 (PinHeader_2x03) — o kiutils caía no pads+halo (falso-negativo F0,
    DRC reprovava courtyards_overlap). Via pcbnew = 6,18×8,71mm (prova viva)."""
    via = pl.courtyards_via_pcbnew([J2])
    assert J2 in via
    x1, y1, x2, y2 = via[J2]
    assert (x2 - x1) == pytest.approx(6.18, abs=0.06)
    assert (y2 - y1) == pytest.approx(8.71, abs=0.06)


@pytest.mark.skipif(paths.ki_python() is None, reason="python do KiCad indisponível")
def test_F7_courtyard_contem_pads():
    """O courtyard (qualquer fonte) tem de CONTER os pads — invariant do guard."""
    ref = "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal"
    pads = pl.pads_do_footprint(ref)
    x1, y1, x2, y2 = pl.courtyard_do_footprint(ref)
    assert min(px for px, _, _ in pads.values()) - 1.0 >= x1
    assert max(px for px, _, _ in pads.values()) + 1.0 <= x2
    assert min(py for _, py, _ in pads.values()) - 1.0 >= y1
    assert max(py for _, py, _ in pads.values()) + 1.0 <= y2


@pytest.mark.skipif(paths.ki_python() is None, reason="python do KiCad indisponível")
def test_F7_otimizar_nunca_fura_borda_nem_piora():
    """Com courtyards REAIS, toda seed: trilhas não crescem + layout na borda.

    Seed 3 provou o bug (trilhas +13,4mm COM violação de borda +500 escondida
    no passe final anti-sobreposição) — a porta de borda fecha isso."""
    netlist = json.loads(EXEMPLO_TI.read_text())
    perfil = {"size_mm": {"w": 80, "h": 50}}
    for seed in (1, 3, 5, 7, 11):
        layout, antes, depois = pl.otimizar(netlist, perfil, seed=seed, iteracoes=200)
        assert depois <= antes + 1e-6, f"seed {seed}: MST cresceu"
        assert pl._fora_da_borda(netlist, layout, 80.0, 50.0) == 0, f"seed {seed}: fora da borda"


def test_F7_clamp_borda_empurra_para_dentro():
    netlist = json.loads(EXEMPLO_TI.read_text())
    # J2 é o maior courtyard (6,2×8,7) — posição forçada no canto extremo
    pos = {c["ref"]: (5.0, 5.0, 0) for c in netlist["components"]}
    pos["J2"] = (0.0, 0.0, 0)
    clamped = pl._clamp_borda(netlist, pos, 80.0, 50.0)
    assert clamped["J2"] != (0.0, 0.0, 0), "J2 em (0,0) fura a margem — tem de ser empurrado"
    assert pl._fora_da_borda(netlist, clamped, 80.0, 50.0) == 0


# ---------- resolver THT + ci (F7, golden I04) ----------

def test_F7_resolver_ne555_dip8():
    s, f, src = resolve.resolver("ci", "NE555", "")
    assert (s, f) == ("Timer:NE555P", DIP8) and src == "override"


def test_F7_resolver_tht_resistor_led():
    s, f, src = resolve.resolver("resistor", "1k", "", montagem="THT")
    assert f == "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal"
    s, f, _ = resolve.resolver("led", "5mm", "", montagem="THT")
    assert f == "LED_THT:LED_D5.0mm"


def test_F7_resolver_capacitor_polarizado_por_valor():
    """10µF ⇒ eletrolítico (CP_Radial); 100nF ⇒ disco (C_Disc) — mesmo type."""
    s, f, _ = resolve.resolver("capacitor", "10uF", "", montagem="THT")
    assert s == "Device:C_Polarized" and f == "Capacitor_THT:CP_Radial_D5.0mm_P2.50mm"
    s, f, _ = resolve.resolver("capacitor", "100nF", "", montagem="THT")
    assert s == "Device:C" and f == "Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P2.50mm"


def test_F7_resolver_borne_tht():
    s, f, _ = resolve.resolver("conector", "borne 2 vias", "", montagem="THT")
    assert f == "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2_1x02_P5.00mm_Horizontal"


def test_F7_resolver_smd_default_intacto_sem_montagem():
    """Retrocompatibilidade: sem montagem, defaults SMD da F1 continuam."""
    s, f, _ = resolve.resolver("led", "vermelho", "")
    assert f == "LED_SMD:LED_0603_1608Metric"


# ---------- brain: refs estáveis + montagem no resolver ----------

def test_F7_brain_montagem_tht_chega_ao_resolver():
    bruto = {"components": [
        {"ref": "R1", "type": "resistor", "value": "1k", "montagem": "THT"},
        {"ref": "U1", "type": "ci", "value": "NE555", "montagem": "THT"},
        {"ref": "C1", "type": "capacitor", "value": "10uF", "montagem": "THT"},
    ], "connections": [{"a": "U1.7", "b": "R1.2", "net_name": "DIS"}]}
    s = __import__("pcbforge.brain", fromlist=["construir_sugestao"]).construir_sugestao(bruto)
    comp = {c["ref"]: c for c in s["components"]}
    assert comp["R1"]["footprint_ref"].startswith("Resistor_THT:")
    assert comp["U1"]["footprint_ref"] == DIP8
    assert comp["C1"]["footprint_ref"] == "Capacitor_THT:CP_Radial_D5.0mm_P2.50mm"
    assert s["connections"][0]["a"]["ref"] == "U1" and s["connections"][0]["a"]["pin"] == "7"


def test_F7_brain_ref_normalizado_maiusculas():
    bruto = {"components": [{"ref": "r1", "type": "resistor", "value": "1k"}],
             "connections": [{"a": "R1.1", "b": "R1.2", "net_name": "X"}]}
    s = __import__("pcbforge.brain", fromlist=["construir_sugestao"]).construir_sugestao(bruto)
    assert s["components"][0]["ref"] == "R1"
    assert len(s["connections"]) == 1

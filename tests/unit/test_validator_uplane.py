"""Testes U01–U08 (Plano Mestre §12.1) — netlist e perfil de placa.

Todos offline (requisito R02): nenhuma rede aqui.
"""
from __future__ import annotations

from pcbforge.core.validator import (
    aplicar_default_espessura,
    validar_netlist,
    validar_perfil,
)


def _netbase():
    return {
        "version": "1.0",
        "components": [
            {"ref": "R1", "type": "resistor", "value": "10k", "symbol_ref": "Device:R",
             "footprint_ref": "Resistor_SMD:R_0603_1608Metric", "pins": [{"number": "1"}, {"number": "2"}]},
            {"ref": "D1", "type": "led", "value": "RED", "symbol_ref": "Device:LED",
             "footprint_ref": "LED_SMD:LED_0603_1608Metric", "pins": [{"number": "1"}, {"number": "2"}]},
        ],
        "connections": [
            {"a": {"ref": "R1", "pin": "2"}, "b": {"ref": "D1", "pin": "2"}, "net_name": "VBUS"},
        ],
        "rails": [{"net": "VBUS", "voltage": 5.0, "current": 0.02}],
    }


def test_u01_parser_basico():
    n = _netbase()
    preos = validar_netlist(n)
    assert not preos, preos
    assert len(n["components"]) == 2 and n["connections"][0]["net_name"] == "VBUS"


def test_u02_ref_duplicado():
    n = _netbase()
    n["components"].append(dict(n["components"][0]))
    codigos = [p["codigo"] for p in validar_netlist(n)]
    assert "REF_DUPLICADO" in codigos


def test_u03_pino_inexistente():
    n = _netbase()
    n["connections"].append({"a": {"ref": "D1", "pin": "4"}, "b": {"ref": "R1", "pin": "1"}, "net_name": "X"})
    codigos = [p["codigo"] for p in validar_netlist(n)]
    assert "PIN_INEXISTENTE" in codigos


def test_u04_rail_sem_fonte():
    n = _netbase()
    n["rails"].append({"net": "+3V3", "voltage": 3.3, "current": 0.1})
    codigos = [p["codigo"] for p in validar_netlist(n)]
    assert "RAIL_SEM_FONTE" in codigos


def test_u05_componente_sem_footprint():
    n = _netbase()
    n["components"][0]["footprint_ref"] = ""
    problemas = validar_netlist(n)
    assert any(p["codigo"] == "PART_SEM_FOOTPRINT" and p["severidade"] == "warning" for p in problemas)


def _perfil(camadas=2):
    return {
        "name": "t", "stackup": {"layers": camadas}, "size_mm": {"w": 50, "h": 30},
        "outline_shape": "retângulo", "mounting": {"diameter_mm": 3.2, "corners": 4, "margin": 3},
        "gold_fingers": False,
    }


def test_u06_defaults_stackup():
    perfil = _perfil(camadas=4)
    codigos = [p["codigo"] for p in validar_perfil(perfil)]
    assert codigos == []
    aplicar_default_espessura(perfil)
    assert perfil["stackup"]["thickness_mm"] == 1.6
    assert perfil["stackup"]["copper_oz"] == 1.0


def test_u07_facesimples_via_proibido():
    perfil = _perfil(camadas=1)
    perfil["autoroute"] = {"layers_allowed": 2}
    codigos = [p["codigo"] for p in validar_perfil(perfil)]
    assert "VIA_EM_FACESIMPLES" in codigos


def test_u08_facesimples_jumper_ok():
    perfil = _perfil(camadas=1)
    perfil["autoroute"] = {"layers_allowed": 1}
    codigos = [p["codigo"] for p in validar_perfil(perfil)]
    assert "VIA_EM_FACESIMPLES" not in codigos


def test_r05_facesimples_goldfingers():
    perfil = _perfil(camadas=1)
    perfil["gold_fingers"] = True
    codigos = [p["codigo"] for p in validar_perfil(perfil)]
    assert "MULTICAMADA_X_GOLDFINGERS" in codigos


def test_r06_cor_fora_da_paleta():
    perfil = _perfil(camadas=2)
    perfil["stackup"]["color"] = "lilás"
    problemas = validar_perfil(perfil)
    assert any(p["codigo"] == "COR_NAO_PADRAO" and p["severidade"] == "warning" for p in problemas)

# Testes ponte 0Ω (F14c — opção §4.3.1(a) do usuário; placa em 1 camada).
# Caso real: semaforo 95×80 1c — nets cruzadas que o roteador não fecha.

from __future__ import annotations

import json

from pcbforge.core import ponte


def _nl_mini():
    return {
        "components": [
            {"ref": "U1", "type": "ci", "value": "esp32",
             "footprint_ref": "RF_Module:ESP32-WROOM-32", "pins": []},
            {"ref": "R5", "type": "resistor", "value": "220",
             "symbol_ref": "Device:R", "source": "kicad-library-tht",
             "footprint_ref": "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal",
             "pins": [{"number": "1"}, {"number": "2"}]},
            {"ref": "D5", "type": "led", "value": "vermelho",
             "symbol_ref": "Device:LED", "source": "kicad-library-tht",
             "footprint_ref": "LED_THT:LED_D5.0mm",
             "pins": [{"number": "1"}, {"number": "2"}]},
        ],
        "connections": [
            {"a": {"ref": "R5", "pin": "1"}, "b": {"ref": "D5", "pin": "1"},
             "net_name": "S2_Y"},
            {"a": {"ref": "U1", "pin": "10"}, "b": {"ref": "R5", "pin": "2"},
             "net_name": "S2_Y"},
        ],
        "rails": []}


def test_I15_ponte_parse():
    assert ponte._parse_preso("S2_Y: R5-1 -> U1-10") == \
        ("S2_Y", "R5", "1", "U1", "10")
    assert ponte._parse_preso("lixão") is None


def test_I15_ponte_insercao_serie():
    nl = _nl_mini()
    refs = ponte.inserir_pontes(
        nl,
        ["S2_Y: U1-10 -> R5-2"],
        {"U1": {"10": (40.0, 30.0)}, "R5": {"2": (20.0, 30.0)}},
    )
    assert refs == ["R1"]                      # ref novo da família
    # componente com pos_mm no MEIO da linha presa
    r = next(c for c in nl["components"] if c["ref"] == "R1")
    assert r["value"] == "0" and r["pos_mm"] == [30.0, 30.0]
    # a conexão presa virou DUAS sub-conexões pela série (U1-10 → R1)
    assert len(nl["connections"]) == 3
    assert {"a": {"ref": "U1", "pin": "10"}, "b": {"ref": "R1", "pin": "1"},
            "net_name": "S2_Y"} in nl["connections"]
    assert {"a": {"ref": "R1", "pin": "2"}, "b": {"ref": "R5", "pin": "2"},
            "net_name": "S2_Y"} in nl["connections"]


def test_I15_ponte_teto_e_grafo_muda():
    nl = _nl_mini()
    pins = {"U1": {"10": (40.0, 30.0)}, "R5": {"2": (20.0, 30.0)}}
    # presos que NÃO são adjacentes na grafo → ingresso (vazio)
    assert ponte.inserir_pontes(nl, ["S2_Y: D5-1 -> R5-1"], pins) == []
    # teto: 1 ponte no max
    nl2 = _nl_mini()
    nl2["connections"] = [
        nl2["connections"][0],
        {"a": {"ref": "U1", "pin": "10"}, "b": {"ref": "R5", "pin": "2"},
         "net_name": "S2_Y"},
        {"a": {"ref": "U1", "pin": "29"}, "b": {"ref": "R11", "pin": "1"},
         "net_name": "S4_Y"},
    ]
    nl2["components"].extend([
        {"ref": "R11", "type": "resistor", "value": "220", "symbol_ref": "Device:R",
         "footprint_ref": "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal",
         "pins": [{"number": "1"}, {"number": "2"}]}])
    pins2 = dict(pins, R11={"1": (50.0, 40.0)})
    refs = ponte.inserir_pontes(nl2, ["S2_Y: U1-10 -> R5-2",
                                      "S4_Y: U1-29 -> R11-1"], pins2, max_pontes=1)
    assert refs == ["R1"]                     # primeira ponte; teto 1 bloqueou a 2ª

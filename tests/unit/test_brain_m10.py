# Testes M10 — brain (F4): unitários, SEM rede (subprocess mockado — o live
# já foi provado interativamente e fica fora da suíte offline).

from __future__ import annotations

import json

import pytest

from pcbforge import brain


JSON_FENCE = """```json
{"omitido": ["frequência"],
 "components": [{"type": "led", "value": "vermelho"}, {"type": "resistor", "value": "470"}],
 "connections": [{"a": "J1.2", "b": "D1.A", "net_name": "SIG"}],
 "board_profile": {"size_mm": {"w": 40, "h": 25}, "camadas": 1}}
```"""


def test_M10_extrai_json_de_fence():
    bruto = brain._extrair_json("textos antes " + JSON_FENCE + " e depois")
    assert bruto and bruto["board_profile"]["camadas"] == 1


def test_M10_extrai_json_sem_fence():
    bruto = brain._extrair_json('lixo {"ok": 1, "a": "b"} lixo')
    assert bruto == {"ok": 1, "a": "b"}


def test_M10_json_quebrado_devolve_none():
    assert brain._extrair_json("sem json nenhum aqui") is None


def test_M10_never_inventa_component(monkeypatch):
    """§13.3: type desconhecido NÃO resolves footprint → needs_review, não cai em
    'qualquer coisa parecida'."""
    bruto = {"components": [{"type": "work-many-things", "value": "x"}], "connections": []}
    mockito = json.dumps({"components": bruto["components"], "connections": []})
    monkeypatch.setattr(brain, "interpretar", lambda p: (json.loads(mockito), []))
    bruto2, _ = brain.interpretar("q")
    s = brain.construir_sugestao(bruto2)
    marca = s["components"][0]
    assert marca.get("needs_review") or not marca["footprint_ref"]


def test_M10_construtor_resolvia_footprints_aptos():
    bruto = {"components": [
        {"type": "led", "value": "vermelho", "ref": "D1"},
        {"type": "resistor", "value": "470", "ref": "R1"},
        {"type": "conector", "value": "2 pinos", "ref": "J1"},
    ], "connections": [{"a": "J1.2", "b": "D1.1", "net_name": "VCC"},
                       {"args": "!", "a": "?", "b": "?", "net_name": "nope"}]}
    s = brain.construir_sugestao(bruto)
    comp = {c["ref"]: c for c in s["components"]}
    assert comp["D1"]["footprint_ref"] == "LED_SMD:LED_0603_1608Metric"
    assert comp["R1"]["footprint_ref"] == "Resistor_SMD:R_0603_1608Metric"
    assert comp["J1"]["footprint_ref"].startswith("Connector_")
    # conexão com endpoints não identificáveis foi descartada (não inventável)
    assert len(s["connections"]) == 1
    cn = s["connections"][0]
    assert cn["a"] == {"ref": "J1", "pin": "2"} and cn["b"] == {"ref": "D1", "pin": "1"}


def test_M10_previa_marcas_needs_review():
    s = {"components": [{"ref": "U1", "type": "ci", "value": "misterioso",
                         "footprint_ref": "", "needs_review": True}],
         "connections": [], "omitido": ["alimenta"], "validador": []}
    texto = brain.propor_previa(s)
    assert "NEEDS_REVIEW" in texto and "pendentes" in texto


def test_M10_prompt_tem_regra_13_3():
    p = brain._prompt("um pedido texto")
    assert "NUNCA invente componente" in p and "SCHEMA" in p


def test_M10_timeout_vira_estado(monkeypatch):
    import subprocess
    def explode(*a, **k):
        raise subprocess.TimeoutExpired(cmd="opencode", timeout=brain.TIMEOUT_S)
    monkeypatch.setattr(subprocess, "run", explode)
    bruto, estados = brain.interpretar("x")
    assert bruto is None and "timeout" in estados  # F14e: + tentativa:<modelo> antes

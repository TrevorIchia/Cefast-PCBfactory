# Testes V-plane da F2 — verify.checklist (Plano Mestre §12.4: V01–V05)
# Unitários: relatórios SINTÉTICOS em pasta temporária — kicad-cli real roda
# apenas no build/golden (build falha em falha de ERC/DRC antes de exportar).

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pcbforge.verify import checklist as vchk


@pytest.fixture()
def placa(tmp_path):
    """Placa sintética com os relatórios verdes."""
    p = tmp_path / "placa-v"
    (p / "verify").mkdir(parents=True)
    (p / "design").mkdir()
    (p / "design" / "netlist.json").write_text(json.dumps({"components": []}))
    (p / "design" / "board_profile.yaml").write_text("stackup:\n  layers: 6\n")
    return p


ERC_OK = {"violations": [], "unconnected_items": []}
DRC_OK = {"violations": [], "unconnected_items": []}


def _escreve(pasta: Path, v: dict):
    for nm, txt in (("erc_report.json", json.dumps(ERC_OK)), ("drc_report.json", json.dumps(v))):
        (pasta / "verify" / nm).write_text(txt)


def test_V01_erc_limpo(placa):
    """V01: erc_report sem erros → item ✅; com 1 erro → item ❌."""
    _escreve(placa, DRC_OK)
    assert vchk.checklist_pre_fab(placa)["itens"][0]["ok"]  # erc
    (placa / "verify" / "erc_report.json").write_text(json.dumps(
        {"violations": [{"severity": "error", "type": "erc"}]}))
    assert not vchk.checklist_pre_fab(placa)["itens"][0]["ok"]


def test_V02_drc_limpo(placa):
    """V02: drc_report sem violações → item ✅; com erro → ❌."""
    _escreve(placa, DRC_OK)
    itens = vchk.checklist_pre_fab(placa)["itens"]
    assert next(i for i in itens if i["id"] == "drc")["ok"]
    _escreve(placa, {"violations": [{"severity": "error", "type": "clearance"}],
                     "unconnected_items": []})
    itens = vchk.checklist_pre_fab(placa)["itens"]
    assert not next(i for i in itens if i["id"] == "drc")["ok"]


def test_V03_drc_violado_conta_somente_erro(placa):
    """V03: clearance violada ERROR conta; warning silk é cosmético (não bloqueia)."""
    _escreve(placa, {"violations": [
        {"severity": "error", "type": "clearance", "description": "x"},
        {"severity": "warning", "type": "silk_overlap", "description": "y"},
    ], "unconnected_items": []})
    res = vchk.checklist_pre_fab(placa)
    drc = next(i for i in res["itens"] if i["id"] == "drc")
    assert not drc["ok"] and "1 bloqueador" in drc["detalhe"]


def test_V04_nets_abertas_listadas(placa):
    """V04: 2 nets abertas → drc ❌ com '2 desconexão(ões)' exato."""
    _escreve(placa, {"violations": [],
                     "unconnected_items": [{"net": "A"}, {"net": "B"}]})
    drc = next(i for i in vchk.checklist_pre_fab(placa)["itens"] if i["id"] == "drc")
    assert not drc["ok"] and "2 desconexão(ões)" in drc["detalhe"]


def test_V05_checklist_camadas(placa):
    """V05: perfil 6 camadas → texto do checklist traz 'copper layers: N'."""
    (placa / "design" / "board_profile.yaml").write_text("stackup:\n  layers: 6\n")
    res = vchk.checklist_pre_fab(placa)
    texto = res["texto"]
    assert "copper layers:" in texto
    camadas = next(i for i in res["itens"] if i["id"] == "camadas")
    assert camadas["detalhe"].startswith("copper layers:")

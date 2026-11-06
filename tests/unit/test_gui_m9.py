# Testes M9 — GUI web (F3): API FastAPI com TestClient (build NÃO é disparado
# nos testes — estes são unitários: sem spawn de pipeline pesado).

from __future__ import annotations

import httpx
import pytest

from fastapi.testclient import TestClient

from pcbforge.gui import app as appmod

CLIENTE = TestClient(appmod.API)


def test_M9_saude():
    r = CLIENTE.get("/api/saude")
    assert r.status_code == 200 and r.json()["ok"]


def test_M9_seeds_projeto_sem_componentes(monkeypatch, tmp_path):
    """Projeto sem netlist de componentes → 422 legível, não IndexError."""
    import json as _json
    pasta = tmp_path / "boards" / "vazio-teste" / "design"
    pasta.mkdir(parents=True)
    (pasta / "netlist.json").write_text(_json.dumps({"components": []}))
    (pasta / "board_profile.yaml").write_text(
        (appmod.ROOT / "boards" / "ex-led-blink-1l" / "design"
         / "board_profile.yaml").read_text())
    monkeypatch.setattr(appmod, "ROOT", tmp_path)
    r = CLIENTE.get("/api/projetos/vazio-teste/seeds")
    assert r.status_code == 422
    assert "sem componentes" in r.json()["detail"]


def test_M9_brain_criar_fluxo(monkeypatch, tmp_path):
    """Aprovação §5.1 passo 5 → boards/<n>/design/{netlist.json, perfil yaml}."""
    import json as _json
    monkeypatch.setattr(appmod, "ROOT", tmp_path)
    sug = {"validador": [], "omitido": ["VCC?"],
           "components": [{"ref": "R1", "type": "resistor", "value": "1k",
                           "pins": [{"number": "1"}, {"number": "2"}]}],
           "connections": [{"a": {"ref": "R1", "pin": "1"},
                            "b": {"ref": "R1", "pin": "2"},
                            "net_name": "VCC"}],
           "perfil": {"camadas": 1, "size_mm": {"w": 50, "h": 30}}}
    import pcbforge.brain as cb
    monkeypatch.setattr(cb, "interpretar", lambda p: ({"fake": True}, []))
    monkeypatch.setattr(cb, "construir_sugestao", lambda b: sug)
    r = CLIENTE.post("/api/brain/criar",
                     json={"pedido": "blink de teste", "nome": "teste-criar"})
    assert r.status_code == 200 and r.json()["criado"] == "teste-criar"
    design = tmp_path / "boards" / "teste-criar" / "design"
    nl = _json.loads((design / "netlist.json").read_text())
    assert nl["components"][0]["ref"] == "R1"
    ys = (design / "board_profile.yaml").read_text()
    assert "layers: 1" in ys and "w: 50" in ys
    # 409 em duplicado
    r2 = CLIENTE.post("/api/brain/criar",
                      json={"pedido": "x", "nome": "teste-criar"})
    assert r2.status_code == 409


def test_M9_brain_criar_nome_invalido():
    r = CLIENTE.post("/api/brain/criar", json={"pedido": "x", "nome": "bad name!"})
    assert r.status_code == 400 and "13.8" in r.json()["detail"]


def test_M9_gate_pre_build_negado(monkeypatch, tmp_path):
    """§19.3: footprints não aptos → 422 nomeando refs, build NUNCA dispara."""
    import json as _json
    from pcbforge.core.validator import aplicar_default_espessura
    pasta = tmp_path / "boards" / "gate-teste" / "design"
    pasta.mkdir(parents=True)
    (pasta / "netlist.json").write_text(_json.dumps({
        "components": [{"ref": "R1", "type": "resistor", "value": "1k",
                        "symbol_ref": "Device:R", "footprint_ref": "",
                        "pins": [{"number": "1"}, {"number": "2"}]}],
        "connections": []}))
    (pasta / "board_profile.yaml").write_text("stackup: {layers: 1}\nsize_mm: {w: 50, h: 30}\n")
    monkeypatch.setattr(appmod, "ROOT", tmp_path)
    r = CLIENTE.post("/api/projetos/gate-teste/build")
    assert r.status_code == 422
    assert "R1" in r.json()["detail"]          # causa nomeada, nunca 'undefined'


def test_M9_index_html():
    r = CLIENTE.get("/")
    assert r.status_code == 200
    assert "PCBForge" in r.text and "<html" in r.text


def test_M9_projetos_lista():
    r = CLIENTE.get("/api/projetos")
    assert r.status_code == 200
    nomes = [p["nome"] for p in r.json()]
    assert "ex-led-blink-1l" in nomes


def test_M9_netlist_get():
    r = CLIENTE.get("/api/projetos/ex-led-blink-1l/netlist")
    assert r.status_code == 200
    dados = r.json()
    assert "components" in dados and "connections" in dados


def test_M9_netlist_put_invalido_nao_salva(monkeypatch):
    r = CLIENTE.put("/api/projetos/ex-led-blink-1l/netlist", json={"components": [], "nonsense": True})
    corpo = r.json()
    assert corpo["salvo"] is False and corpo["problemas"]


def test_M9_perfil_get():
    r = CLIENTE.get("/api/projetos/ex-led-blink-1l/perfil")
    assert r.status_code == 200 and "stackup" in r.json()["yaml"]


def test_M9_perfil_put_yaml_ruim():
    r = CLIENTE.put("/api/projetos/ex-led-blink-1l/perfil",
                    json={"yaml": "stackup: [a: [b"})
    corpo = r.json()
    assert corpo["salvo"] is False and corpo["problemas"][0]["codigo"] == "YAML"


def test_M9_protecao_nome_arbitrario():
    """§13.8: sem path traversal — nome com '/' ou '..' é rejeitado."""
    assert CLIENTE.get("/api/projetos/..%2Fetc/netlist").status_code in (400, 404)
    assert CLIENTE.get("/api/projetos/foo bar/netlist").status_code == 400


def test_M9_projeto_inexistente_404():
    assert CLIENTE.get("/api/projetos/placa-que-nao-existe/netlist").status_code == 404


def test_M9_seeds_viabilidade():
    r = CLIENTE.get("/api/projetos/ex-led-blink-1l/seeds")
    assert r.status_code == 200
    s = r.json()["seeds"]
    assert len(s) == 8 and all("viavel_1l" in x for x in s)


def test_M9_renders_e_zip():
    r = CLIENTE.get("/api/projetos/ex-led-blink-1l/renders")
    assert r.status_code == 200 and r.json()["renders"]
    z = CLIENTE.get("/api/projetos/ex-led-blink-1l/zip")
    assert z.status_code == 200 and z.headers["content-type"] == "application/zip"


def test_M9_build_status_sem_andamento():
    r = CLIENTE.get("/api/projetos/ex-led-blink-1l/build/status")
    assert r.status_code == 200
    d = r.json()
    assert set(d) >= {"build", "log", "checklist"}

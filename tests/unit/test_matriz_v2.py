# Testes da matriz v2 — 5 modelos de placa novos (pedido do usuário:
# "variar os testes pra cobrir mais escopos"): PTH/SMD, 1c/2c, misto,
# sanduíche (BTB), CIs de poucos e de muitos pinos.
# Sanidade de schema + invariants da matriz — builds E2E rodam à parte.

from __future__ import annotations

import json
from pathlib import Path

import yaml

from pcbforge.core import validator as v
from pcbforge.core.placement import contar_conflitos, coords_pads, otimizar

BOARDS = ["ex-lm358-amp-1l", "ex-shift595-8led-1l", "ex-ne555-misto-2l",
          "ex-shield-sanduiche-2l", "ex-stm32-lqfp48-2l"]
BASE = Path(__file__).resolve().parents[2] / "boards"


def _load(nome: str):
    d = BASE / nome / "design"
    nl = json.loads((d / "netlist.json").read_text())
    pf = yaml.safe_load((d / "board_profile.yaml").read_text())
    return nl, pf


def test_MV01_validador_verde_nas_5():
    for nome in BOARDS:
        nl, pf = _load(nome)
        probs = v.validar_netlist(nl) + v.validar_perfil(pf)
        erros = [p for p in probs if p["severidade"] == "erro"]
        assert not erros, f"{nome}: {erros}"


def test_MV02_toda_conexao_aponta_para_pin_declarado():
    for nome in BOARDS:
        nl, _ = _load(nome)
        pins = {c["ref"]: {p["number"] for p in c.get("pins", [])} for c in nl["components"]}
        for k in nl["connections"]:
            for end in (k["a"], k["b"]):
                assert end["ref"] in pins, f"{nome}: ref {end['ref']} não declarado"
                assert str(end["pin"]) in pins[end["ref"]], \
                    f"{nome}: pin {end['ref']}.{end['pin']} não declarado"


def test_MV03_rails_tem_conexao():
    for nome in BOARDS:
        nl, _ = _load(nome)
        nets = {k["net_name"] for k in nl["connections"]}
        for r in nl.get("rails", []):
            assert r["net"] in nets, f"{nome}: rail {r['net']} sem conexão"


def test_MV04_camadas_da_matriz_e_conectores_fixos():
    """A matriz existe pra cobrir escopos: camadas exatas por board + regra
    A3/A7 aplicada (todo conector fixo na borda com pos_mm)."""
    camadas = {"ex-lm358-amp-1l": 1, "ex-shift595-8led-1l": 1, "ex-ne555-misto-2l": 2,
               "ex-shield-sanduiche-2l": 2, "ex-stm32-lqfp48-2l": 2}
    for nome in BOARDS:
        nl, pf = _load(nome)
        assert int(pf["stackup"]["layers"]) == camadas[nome], nome
        fixos = [c for c in nl["components"] if c.get("fixo")]
        assert fixos, f"{nome}: matriz v2 exige conectores fixos (A3/A7)"
        for c in fixos:
            assert c.get("pos_mm"), f"{nome}: fixo {c['ref']} sem pos_mm"


def test_MV05_placement_tem_seed_verde():
    """§4.3.2b agora gira seeds no placement — cada board da matriz precisa
    de pelo menos 1 seed com 0 sobreposições entre (8, 9, 10)."""
    for nome in BOARDS:
        nl, pf = _load(nome)
        verdes = 0
        for seed in (8, 9, 10):
            layout = otimizar(nl, pf, seed=seed, iteracoes=600)[0]
            if contar_conflitos(coords_pads(nl, layout)[1]) == 0:
                verdes += 1
        assert verdes >= 1, f"{nome}: nenhuma seed verde em (8,9,10)"

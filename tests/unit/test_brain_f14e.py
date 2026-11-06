# Testes F14e — brain "se-vira sozinho" (método geral + ferramentas).
# Unitários, SEM rede (subprocess mockado — doutrina test_brain_m10).

from __future__ import annotations

import json

import pytest

from pcbforge import brain
from pcbforge.parts import catalogo
from pcbforge.parts.resolve import normalizar_tipo, resolver


def _apto(fp: str) -> bool:
    return bool(fp) and catalogo.apto(fp)


def test_F14e_resolver_switch_smd_ht():
    s, fp, src = resolver("switch", "tátil", "", "SMD", 4)
    assert src == "kicad-library" and s == "Switch:SW_Push" and _apto(fp)
    s, fp, src = resolver("tecla", "", "", "THT", 0)
    assert src == "kicad-library-tht" and "SW_PUSH" in fp and _apto(fp)


@pytest.mark.parametrize("tipo,mont", [
    ("cristal", "SMD"), ("crystal", "THT"),
    ("mosfet", "SMD"), ("transistor", "THT"),
    ("fuse", "SMD"), ("fusível", "THT"),
    ("buzzer", "SMD"), ("bateria", "pilha"),
])
def test_F14e_resolver_tipos_novos_apto(tipo, mont):
    _, fp, src = resolver(tipo, "", "", mont if mont in ("SMD", "THT") else "SMD", 2)
    assert src in ("kicad-library", "kicad-library-tht"), f"{tipo}/{mont}: src={src}"
    assert _apto(fp), f"{tipo}/{mont}: footprint {fp} não apto (§19.2)"


def test_F14e_conector_generico_nxp():
    s, fp, src = resolver("conector", "4 pinos", "", "SMD", 0)
    assert s.endswith("Conn_01x04") and _apto(fp) and src == "kicad-library"
    s, fp, src = resolver("conector", "", "", "THT", 6)   # N do nº de pins
    assert "01x06" in s and "MKDS-1,5-6" in fp and _apto(fp)
    s, fp, src = resolver("conector", "", "", "SMD", 0)   # sem pista → default 2
    assert s.endswith("Conn_01x02") and _apto(fp)
    # borne de parafuso → terminal block THT mesmo em SMD pedido por texto


def test_F14e_override_usb_lowercase():
    """Lição F14e: override USB tinha chave 'USB' (maiúscula) contra val
    minúsculo — NUNCA casava. Agora dispensa receptáculo C APTO."""
    s, fp, src = resolver("conector", "USB tipo C", "", "SMD", 0)
    assert src == "override" and "USB_C" in s and _apto(fp)


def test_F14e_zener_no_value_vira_d_symbol():
    s, fp, src = resolver("diodo", "zener 5v1", "", "SMD", 2)
    assert s == "Device:D_Zener" and _apto(fp)


def test_F14e_normalizar_tipo_alias():
    assert normalizar_tipo("botão") == "switch"
    assert normalizar_tipo("tecla") == "switch"
    assert normalizar_tipo("fusível") == "fuse"
    assert normalizar_tipo("pilha") == "bateria"
    assert normalizar_tipo("microcontrolador") == "ci"
    assert normalizar_tipo("coisa-estranha") == "coisa-estranha"


def test_F14e_rascunho_completo_tipos_sinonimos():
    """Caso-teclado embrionário: type 'tecla' (sinônimo) + switch + diodo —
    TODAS as peças entram na sugestão (nenhuma descartada), needs_review
    preservado quando o modelo marcou, e refs auto SW/D."""
    bruto = {
        "decisoes_padrao": ["matriz 4x4 = 16 teclas com 1N4148 por tecla"],
        "omitido": ["a", "b", "c", "d", "e"],
        "components": [
            {"type": "tecla", "value": "SW_Push", "montagem": "SMD"},
            {"type": "switch", "value": "reset", "needs_review": True},
            {"type": "diodo", "value": "1N4148", "ref": "D1"},
        ],
        "connections": [{"a": "SW1.2", "b": "D1.1", "net_name": "COL1"}],
    }
    s = brain.construir_sugestao(bruto)
    refs = {c["ref"]: c for c in s["components"]}
    assert set(refs) == {"SW1", "SW2", "D1"}          # nada descartado
    assert refs["SW1"]["footprint_ref"].startswith("Button_Switch_")
    assert not refs["SW1"].get("needs_review")         # resolvida APTO, não marca
    assert refs["SW2"].get("needs_review")            # vindo do modelo, preserva
    assert len(s["omitido"]) == 3                     # cap ≤ 3
    assert any(p.get("codigo") == "OMITIDO_CAP" for p in s["validador"])
    assert s["decisoes_padrao"] == ["matriz 4x4 = 16 teclas com 1N4148 por tecla"]
    assert len(s["connections"]) == 1                 # SW1.2 ↔ D1.1 intacta


def test_F14e_refs_auto_tipos_novos():
    bruto = {"components": [
        {"type": "cristal", "value": "12 MHz"}, {"type": "mosfet", "value": "IRLML"},
        {"type": "fuse", "value": "2 A"}, {"type": "buzzer", "value": "5 V"},
        {"type": "bateria", "value": "AA"},
    ], "connections": []}
    s = brain.construir_sugestao(bruto)
    refs = {c["ref"] for c in s["components"]}
    assert refs == {"Y1", "Q1", "F1", "BZ1", "BT1"}
    for c in s["components"]:                          # todos resolveram APTO
        assert c["footprint_ref"] and not c.get("needs_review"), c


def test_F14e_pins_compactos_expandem_localmente():
    assert brain._expande_pins(4) == [{"number": "1"}, {"number": "2"},
                                      {"number": "3"}, {"number": "4"}]
    assert brain._expande_pins("1..3") == [{"number": "1"}, {"number": "2"},
                                           {"number": "3"}]
    assert brain._expande_pins([{"number": "1..2"}, {"number": "5"}]) == [
        {"number": "1"}, {"number": "2"}, {"number": "5"}]
    # descritas verbatim: passam ITA (nunca adivinha — §13.3)
    verbatim = [{"number": "EN"}, {"number": "GND"}]
    assert brain._expande_pins(verbatim) == verbatim
    # resolver APTO com pins compacto (TQFP-32 do ATmega)
    bruto = {"components": [{"type": "ci", "value": "ATmega328P (TQFP-32)", "pins": 32}],
             "connections": []}
    c0 = brain.construir_sugestao(bruto)["components"][0]
    assert len(c0["pins"]) == 32 and c0["footprint_ref"].startswith("Package_"), c0


def test_F14e_fallback_cadeia_modelos_free(monkeypatch):
    """Cota free é POR MODELO (prova 02-11): quota estourada num modelo
    NÃO trava — o brain tenta o próximo free em cadeia."""
    seq = [(None, ["tentativa:x", "quota_free_excedida", "opencode_exit_1"]),
           ({"components": [{"type": "led"}]}, ["tentativa:y", "ok"])]
    vistos = []
    monkeypatch.setattr(brain, "_executar", lambda args, modelo:
                        (vistos.append(modelo) or seq[len(vistos) - 1]))
    bruto, estados = brain.interpretar("pedido")
    assert bruto == {"components": [{"type": "led"}]}
    assert vistos[:2] == [brain.MODELOS_FREE[0], brain.MODELOS_FREE[1]]
    assert any(e.startswith("modelo:") for e in estados)


def test_F14e_fallback_para_em_erro_real(monkeypatch):
    """Timeout/JSON inválido não é cota: cadeia não gasta os outros modelos."""
    calls = []
    monkeypatch.setattr(brain, "_executar",
                        lambda args, m: (calls.append(m) or
                                         (None, ["tentativa:x", "timeout"])))
    bruto, estados = brain.interpretar("pedido")
    assert bruto is None and len(calls) == 1 and "timeout" in estados


def test_F14e_prompt_e_procedimento():
    p = brain._prompt("teclado")
    assert "RASCUNHO COMPLETO" in p and "NUNCA invente componente" in p
    assert "MÁXIMO 3" in p and "decisoes_padrao" in p
    assert "switch" in p and "cristal" in p and "fuse" in p
    assert "SCHEMA" in p
    assert "switch" in brain.ENUM_TIPOS and "bateria" in brain.ENUM_TIPOS


def test_F14e_gui_gate_bloqueia_apenas_rascunho_vazio(monkeypatch):
    from pcbforge.gui.app import _bloqueio_criacao
    vazio = {"components": [], "validador": []}
    draft = {"components": [{"ref": "SW1", "needs_review": True,
                             "footprint_ref": "", "type": "switch"}],
             "validador": [{"codigo": "U04", "severidade": "erro",
                            "mensagem": "sem footprint"}]}
    assert _bloqueio_criacao(vazio) != []              # U00 real bloqueia
    assert _bloqueio_criacao(draft) == []              # draft parcial passa


def test_F14e_gui_cache_reaproveita_previa(monkeypatch):
    """O /criar NÃO re-interpreta com o modelo: usa a sugestão da prévia."""
    from pcbforge.gui import app as appl
    bruto = {"components": [{"type": "led", "value": "vermelho", "ref": "D1"}],
             "connections": [], "omitido": ["x"]}
    chamadas = []
    monkeypatch.setattr(brain, "interpretar",
                        lambda p: (chamadas.append(p) or (json.loads(json.dumps(bruto)), [])))
    resp = appl.brain_endpoint({"pedido": "led 5mm no painel"})
    assert chamadas == ["led 5mm no painel"]
    assert appl._cache_sugestao["led 5mm no painel"] == resp["sugestao"]
    # segunda chamada /criar com o MESMO pedido → cache virado, sem nova chamada
    sug = appl._cache_sugestao.get("led 5mm no painel")
    assert sug["components"][0]["ref"] == "D1"

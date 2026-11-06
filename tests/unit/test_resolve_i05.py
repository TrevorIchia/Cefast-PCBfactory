# I05 — "todos os e se" do resolver (pedido LM386 do usuário, outro LoaderLost):
# e se o MPN não estiver no mapa? e se o pacote só existir em variante? e se
# o nº de pinos for a única pista? e se cerâmico tiver µF com vírgula?

from __future__ import annotations

from pcbforge.core.validator import validar_netlist
from pcbforge.parts.resolve import resolver


def test_I05_override_mpn_lm386():
    assert resolver("ci", "LM386 (DIP-8)", "", "THT") == (
        "Amplifier_Audio:LM386", "Package_DIP:DIP-8_W7.62mm", "override")


def test_I05_potenciometro_nao_e_resistor():
    sym, fp, src = resolver("resistor", "10 kΩ potenciômetro (3 pinos)", "", "THT")
    assert "R_Potentiometer" in sym and "Potentiometer" in fp and src != "needs_review"
    # tipo direto também
    assert "R_Potentiometer" in resolver("potenciometro", "10k", "", "THT")[0]


def test_I05_ceramico_com_microuf_e_virgula_e_polarizado_nao():
    # "0,1 µF cerâmico" tem de ficar Device:C (disc), NÃO CP eletrolítico
    sym, fp, _ = resolver("capacitor", "0,1 µF 50 V cerâmico", "", "THT")
    assert sym == "Device:C" and "C_Disc" in fp
    # e o eletrolítico continua polarizado
    assert "Polarized" in resolver("capacitor", "10 µF eletrolítico", "", "THT")[0]


def test_I05_ci_mpn_desconhecido_pacote_no_value():
    sym, fp, src = resolver("ci", "UM1234 misterioso (SOIC-8)", "", "THT")
    assert sym == "" and src == "needs_review"
    assert fp.startswith("Package_SO:SOIC-8")      # inferido do pacote


def test_I05_ci_desconhecido_inferencia_por_pinos():
    sym, fp, src = resolver("ci", "chip genérico", "", "THT", pins=8)
    assert "DIP-8" in fp and src == "needs_review"


def test_I05_ci_sem_pacote_sem_pinos_needs_review_limpio():
    assert resolver("ci", "chip desconhecido", "", "THT") == ("", "", "needs_review")


def test_I05_validator_warning_nao_bloqueia_aprovacao():
    """bloqueios = somente severidade erro (§5.1: usuário aprova warnings)."""
    nl = {"components": [{"ref": "IC1", "type": "ci", "value": "x",
                          "symbol_ref": "A:B", "footprint_ref": "", "pins": []}],
          "connections": [], "rails": []}
    probs = validar_netlist(nl)
    assert any(p["codigo"] == "PART_SEM_FOOTPRINT"
               and p["severidade"] == "warning" for p in probs)


def test_I13_peca_sem_symbol_nem_fp_e_ERRO_bloqueio():
    """Peça sem identidade elétrica = erro (semaforo: U1/U2 nasceram vazios)."""
    nl = {"components": [{"ref": "U1", "type": "ci", "value": "x",
                          "symbol_ref": "", "footprint_ref": "", "pins": []}],
          "connections": [], "rails": []}
    probs = validar_netlist(nl)
    assert any(p["codigo"] == "PART_SEM_FOOTPRINT"
               and p["severidade"] == "erro" for p in probs)


def test_I13_resolver_semaforo_esp32_ams1117():
    """Caso real do semáforo (I05): ESP32 com 3D apto + AMS1117-3.3 SOT-223."""
    sym, fp, src = resolver("ci", "ESP32-WROOM-32 (38)", "", "SMD")
    assert (sym, fp) == ("RF_Module:ESP32-WROOM-32", "RF_Module:ESP32-WROOM-32")
    assert src == "override"
    sym, fp, src = resolver("ci", "AMS1117-3.3 (SOT-223)", "", "SMD", pins=3)
    assert sym == "Regulator_Linear:AMS1117-3.3"
    assert "SOT-223" in fp and src == "kicad-library"

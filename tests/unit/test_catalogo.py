# Testes do módulo parts.catalogo — Plano Mestre §12.2 (nível 2)
# F1 — limpa de componentes: só os footprints aptos respondem; exceção
# MountingHole; fallback de resolve nunca inventa componente (§13.3).

from __future__ import annotations

import pytest

from pcbforge.parts import catalogo
from pcbforge.parts import resolve


@pytest.fixture(scope="module", autouse=True)
def _catalogo_real():
    """Garante catalogo.json existente (gera se faltar — censo rápido ~40s)."""
    if not catalogo.CATALOGO_PATH.is_file():
        catalogo.gerar_catalogo()
    catalogo.carregar()
    yield


def test_C01_total_da_ordem_da_centena():
    cat = catalogo.carregar()
    assert 7000 <= len(cat) <= 8500, f"censo desacordo com F0 ({len(cat)})"


def test_C02_defaults_resolvidos_sao_aptos():
    for tipo, d in resolve.DEFAULTS.items():
        fp = resolve._filtrar_aptos(d["footprint"])
        assert fp is not None, f"default de {tipo} غير apto: {d['footprint']}"
        assert catalogo.apto(fp), f"resposta filtrada não está no catálogo: {fp}"


def test_C03_excecao_montinghole():
    assert catalogo.apto("MountingHole:MountingHole_3.2mm_M3")
    ficha = catalogo.info("MountingHole:MountingHole_3.2mm_M3")
    assert ficha["puro_furo"] and not ficha["step"]


def test_C04_inexistente_nao_e_apto():
    assert not catalogo.apto("Resistor_SMD:R_X342_NAOEXISTE")
    assert catalogo.info("Resistor_SMD:R_X342_NAOEXISTE") is None


def test_C05_alternativas_mesma_lib():
    alts = catalogo.alternativas("Resistor_SMD:R_0603_1608Metric")
    assert all(a.startswith("Resistor_SMD:") for a in alts)
    assert "Resistor_SMD:R_0805_2012Metric" in alts   # 0805 → 2012 no sistema métrico
    melhor = catalogo.melhor_alternativa("Resistor_SMD:R_0603_1608Metric")
    assert melhor in alts


def test_C06_resolver_nunca_solta_footprint_nao_apto(monkeypatch):
    # default "inaptinho" hábil: fabrica footprint não existente → resolver
    # precisa filtrar p/ alternativa da mesma lib ou needs_review
    d_original = dict(resolve.DEFAULTS)
    monkeypatch.setitem(resolve.DEFAULTS, "resistor",
                        {"symbol": "Device:R", "footprint": "Resistor_SMD:R_NAOEXISTE_9x9mm"})
    s, f, fonte = resolve.resolver("resistor", "10k")
    assert f == "" or catalogo.apto(f), "resolver soltou footprint não apto"
    assert fonte == "needs_review" or (f and catalogo.apto(f))

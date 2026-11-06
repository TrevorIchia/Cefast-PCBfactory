# Testes U/P do módulo parts.lcsc — Plano Mestre §12.2 (nível 2)
# Todas as chamadas de rede são ESCOLHIDAS (mockadas) — os testes offline,
# conforme requisito R02 do plano.

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

import pytest

from pcbforge.parts import lcsc


@pytest.fixture()
def cache_tmp(tmp_path, monkeypatch):
    lcsc.LIBCACHE = tmp_path / "libcache"
    lcsc._state.update(última_req=0.0, cooldown_ate=0.0)  # zera globais entre testes
    return tmp_path


SUCCESS = {"success": True, "result": {"components": [{"description": "10k RES"}]}}
NOT_FOUND = {"success": False, "message": "Component not found"}


def _resp_mock(status=200, corpo=SUCCESS):
    import urllib.error

    if status != 200:
        return urllib.error.HTTPError(url="x", code=status, msg="e", hdrs=None, fp=None)
    return json.dumps(corpo).encode()


class _RespFake:
    def __init__(self, corpo): self._c = corpo
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return self._c
    status = 200


def test_p01_cache_hit(cache_tmp, monkeypatch):
    """P02: mesma busca duas vezes → 2ª vem do cache, sem rede."""
    chamadas = []
    monkeypatch.setattr(lcsc, "API_ENDPOINT", "teste://x/{lcsc_id}")
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: chamadas.append(1) or _RespFake(_resp_mock(200)))
    monkeypatch.setattr(lcsc, 'MIN_INTERVAL_S', 0)  # agiliza testes (auto-restaura)

    est1, d1 = lcsc.buscar("C22222")
    est2, d2 = lcsc.buscar("C22222")
    assert est1 == lcsc.FerrEstado.REDE
    assert est2 == lcsc.FerrEstado.CACHE
    assert d1 == d2
    assert len(chamadas) == 1, "segunda chamada NÃO deve tocar a rede"


def test_p02_cooldown_em_403(cache_tmp, monkeypatch):
    """R-defesa HTTP 403 ativa cooldown e a próxima chamada devolve COOLDOWN."""
    import urllib.error
    monkeypatch.setattr(lcsc, "API_ENDPOINT", "teste://x/{lcsc_id}")
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(
        urllib.error.HTTPError(url="x", code=403, msg="waf", hdrs=None, fp=None)))
    monkeypatch.setattr(lcsc, 'MIN_INTERVAL_S', 0)
    est1, d1 = lcsc.buscar("C11111")
    assert est1 == lcsc.FerrEstado.COOLDOWN and d1 is None

    est2, d2 = lcsc.buscar("C22222")   # nem tenta rede — cooldown global
    assert est2 == lcsc.FerrEstado.COOLDOWN and d2 is None


def test_p03_inexistente(cache_tmp, monkeypatch):
    monkeypatch.setattr(lcsc, "API_ENDPOINT", "teste://x/{lcsc_id}")
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _RespFake(_resp_mock(200, NOT_FOUND)))
    monkeypatch.setattr(lcsc, 'MIN_INTERVAL_S', 0)
    est, d = lcsc.buscar("C12345")
    assert est == lcsc.FerrEstado.INEXISTENTE and d is None


# ——— P04 (F1): baixar_part offline via libcache real dos artefatos C8734 (evidência de download) ———

LIBCACHE_REAL = Path(__file__).resolve().parents[2] / "libcache" / "lcsc"


def test_p04_baixar_part_offline():
    if not (LIBCACHE_REAL / "C8734.kicad_sym").exists():
        pytest.skip("libcache C8734 indisponível (evidência de download não preservada)")
    lcsc.LIBCACHE = LIBCACHE_REAL
    p = lcsc.baixar_part("C8734")
    assert p["estados"] == []
    assert p["fonte"] == "lcsc-cache"          # SEM rede
    assert p["symbol_ref"] == "LCSC:C8734"
    assert p["footprint_ref"].startswith("LCSC:")
    assert p["model3d"].endswith(".step")


def test_p04b_baixar_part_inexistente_nunca_crasha():
    if time.monotonic() < lcsc._state.get("cooldown_ate", 0):
        pytest.skip("cooldown ativo pós WAF")
    r = lcsc.baixar_part("C00000X")            # parte inexistente: estados, não exceção
    assert r["estados"]  # §9: modos de falha sempre devolvidos

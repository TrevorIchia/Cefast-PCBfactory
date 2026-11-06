# Testes M11 — pcbforge.paths (F5 — instalador universal): descoberta dinâmica
# de raiz/KiCad substitui caminhos fixos de usuário (§18 — Rota B universal).

from __future__ import annotations

from pathlib import Path

import pytest

from pcbforge import paths


@pytest.fixture(autouse=True)
def _limpa_cache_kicad(monkeypatch):
    paths.kicad_shared.cache_clear()
    yield
    paths.kicad_shared.cache_clear()


def test_M11_root_dinamica():
    r = paths.root()
    assert r.name == "pcbforge" and (r / "pcbforge" / "cli.py").is_file()
    assert paths.libcache() == r / "libcache"


def test_M11_kicad_shared_achado_local():
    """Nesta máquina (mac, KiCad 10.0.7) a descoberta acha SharedSupport real."""
    sh = paths.kicad_shared()
    assert sh is not None
    for sub in ("symbols", "footprints", "3dmodels"):
        assert (sh / sub).is_dir(), f"falta {sub} em {sh}"


def test_M11_env_override_manda(monkeypatch, tmp_path):
    """PCBFORGE_KICAD_DIR apontando p/ SharedSupport válido vence tudo."""
    fake = tmp_path / "SharedSupport"
    for sub in ("symbols", "footprints"):
        (fake / sub).mkdir(parents=True)
    monkeypatch.setenv("PCBFORGE_KICAD_DIR", str(fake))
    assert paths.kicad_shared() == fake


def test_M11_env_inexistente_ignora(monkeypatch):
    """Caminho inválido no env não vira resposta (cai nos candidatos padrão)."""
    monkeypatch.setenv("PCBFORGE_KICAD_DIR", "/kicad/que/nao/existe/x")
    sh = paths.kicad_shared()
    assert sh is None or (sh / "symbols").is_dir() and (sh / "footprints").is_dir()
    assert len(paths._candidatos_shared()) >= 1

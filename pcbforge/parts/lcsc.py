"""parts.lcsc — resolver componentes LCSC/EasyEDA para KiCad (M2).

Defesas anti-WAF (descobertas experimentais em 2026-10-28):
  1. Intervalo mínimo entre requisições (LCSC_MIN_INTERVAL_S, default 3 s)
  2. Cooldown global em HTTP 403 (pode levar minutos; não insistimos)
  3. Cache agressivo em libcache/lcsc/ (componente resolvido nunca é re-baixado)

Endpooints usados (api v1 pública, sem auth):
  GET https://easyeda.com/api/products/{C-id}/components  (símbolo+footprint JSON)
  GET https://easyeda.com/api/products/{C-id}/svgs         (vista 2D do símbolo)
  GET https://modules.easyeda.com/3dmodel/{uuid}           (módulo 3D — nem toda peça tem)
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from enum import Enum
from pathlib import Path

from pcbforge import paths

API_ENDPOINT = "https://easyeda.com/api/products/{lcsc_id}/components"

MIN_INTERVAL_S = 3.0        # defesa #1: 20/min => rajada evitada
COOLDOWN_403_S = 300.0      # defesa #2: 5 min de pausa global após 403
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"

_HEADERS = {
    "Accept": "*/*",
    "Accept-Encoding": "identity",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "Referer": "https://easyeda.com/",
    "User-Agent": USER_AGENT,
}

_state = {"última_req": 0.0, "cooldown_ate": 0.0}

LIBCACHE = paths.libcache() / "lcsc"


class FerrEstado(Enum):
    """Resultado do resolver de componente."""

    CACHE = "cache"            # veio do cache local
    REDE = "rede"              # baixado ao vivo
    COOLDOWN = "cooldown"      # WAF em pausa — retente mais tarde (defesa #2)
    INEXISTENTE = "inexistente"  # API respondeu "Component not found"
    ERRO = "erro"


def _dormir_intervalo() -> None:
    """Defesa #1: espera até cumprir o intervalo mínimo entre requisições."""
    agora = time.monotonic()
    delta = MIN_INTERVAL_S - (agora - _state["última_req"])
    if delta > 0:
        time.sleep(delta)
    _state["última_req"] = time.monotonic()


def buscar(lcsc_id: str) -> tuple[FerrEstado, dict | None]:
    """Busca o JSON de componente da LCSC.  Retorna (estado, dados|None).

    Nunca levanta exceção — todos os modos de falha são estados explícitos
    (regra do Plano Mestre §9: modos de falha sempre devolvidos, nunca crash).
    """
    cache = LIBCACHE / f"{lcsc_id}.json"
    if cache.exists():                                   # defesa #3
        return FerrEstado.CACHE, json.loads(cache.read_text(encoding="utf-8"))

    if time.monotonic() < _state["cooldown_ate"]:
        return FerrEstado.COOLDOWN, None

    _dormir_intervalo()
    try:
        req = urllib.request.Request(API_ENDPOINT.format(lcsc_id=lcsc_id), headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 403:
            _state["cooldown_ate"] = time.monotonic() + COOLDOWN_403_S
        return FerrEstado.COOLDOWN if e.code == 403 else FerrEstado.ERRO, None
    except (OSError, ValueError, json.JSONDecodeError):
        return FerrEstado.ERRO, None

    if not payload.get("success"):
        return FerrEstado.INEXISTENTE, None

    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return FerrEstado.REDE, payload


def baixar_part(lcsc_id: str) -> dict:
    """Baixa symbol + footprint + 3D (STEP/WRL) de uma peça LCSC → libcache/lcsc/.

    Usa o easyeda2kicad (open source, aprovado no Plano Mestre §6.1 item 3) via
    subprocess. Idempotente: se os 3 artefatos já existem no libcache, devolve
    o mesmo caminho SEM rede (P04 — offline).
    Devolve {symbol_ref, footprint_ref, model3d, fonte, estado[]} — estado vazio
    = sucesso; caso contrário lista os modos de falha (§9: nunca crash).
    """
    estados: list[str] = []
    base = LIBCACHE / lcsc_id
    sym = base.with_suffix(".kicad_sym")
    pretty = LIBCACHE / f"{lcsc_id}.pretty"
    modelos3d = list(LIBCACHE.glob(f"{lcsc_id}.3dshapes/*.step"))
    if sym.exists() and pretty.exists() and modelos3d:
        kicad_mod = next(pretty.glob("*.kicad_mod"), None)
        if kicad_mod:
            return {
                "symbol_ref": f"LCSC:{sym.stem}",
                "footprint_ref": f"LCSC:{kicad_mod.stem}",
                "model3d": str(modelos3d[0]),
                "fonte": "lcsc-cache",
                "estados": [],
            }

    # defesas WAF (#1/#2) compartilhadas com buscar()
    if time.monotonic() < _state["cooldown_ate"]:
        estados.append("cooldown")
        return {"fonte": "lcsc", "estados": estados}
    _dormir_intervalo()
    cmd = [sys.executable, "-m", "easyeda2kicad",
           "--full", "--lcsc_id", lcsc_id,
           "--output", str(sym), "--overwrite"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return {"fonte": "lcsc", "estados": ["timeout"]}
    saida = (r.stdout or "") + (r.stderr or "")
    sim_ok = sym.exists()
    kicad_mod = next(pretty.glob("*.kicad_mod"), None) if pretty.exists() else None
    modelos3d = list(LIBCACHE.glob(f"{lcsc_id}.3dshapes/*.step"))
    if not (sim_ok and kicad_mod and modelos3d):
        estados.append("falha_baixa")
        if "[ERROR] Failed to fetch" in saida:
            estados.append("api_falha")
        return {"fonte": "lcsc", "estados": estados, "log": saida[-500:]}
    return {
        "symbol_ref": f"LCSC:{sym.stem}",
        "footprint_ref": f"LCSC:{kicad_mod.stem}",
        "model3d": str(modelos3d[0]),
        "fonte": "lcsc",
        "estados": [],
    }


def resetar_cooldown(teste: bool = False) -> None:
    """Reseta o cooldown global (uso em testes ou após troca de rede)."""
    _state["cooldown_ate"] = 0.0

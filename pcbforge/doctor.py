#!/usr/bin/env python3
"""pcbforge doctor — verifica o ambiente conforme o Plano Mestre (§2/§17 F5).

Roda com a stdlib pura (independente do venv), para poder diagnosticar o
próprio processo de instalação — é o passo final do instalador universal
(install.sh / install.ps1): sucesso = zero itens 🔴. Cross-plataforma: mac,
Linux e Windows (venv .venv/Scripts/python.exe, KiCad em Program Files…).
"""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # raiz: importa pacote pcbforge

from pcbforge import paths  # noqa: E402

ROOT = paths.root()
VENV = ROOT / ".venv"


def _py_venv() -> Path:
    if sys.platform in ("win32", "cygwin"):
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def run(cmd: str) -> str | None:
    """Executa comando, devolvendo primeira linha de stdout ou None."""
    try:
        out = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip().split("\n")[0]
        return None
    except (subprocess.TimeoutExpired, OSError):
        return None


CHECKS: list[tuple[str, str, str, str]] = []
"""Tabela de verificações: (item, estado, detalhe, emoji)."""


def add(item: str, ok: bool, estado: str, detalhe: str) -> None:
    s = "🟢" if ok else ("🟡" if estado == "amarelo" else "🔴")
    CHECKS.append((item, estado, detalhe, s))


def main() -> int:
    print(f"\n📋 pcbforge doctor — diagnóstico do ambiente ({ROOT})\n" + "=" * 72)

    # 1. Estrutura raiz
    dirs = ["pcbforge", "tests", "docs", "tools", "scripts", "examples", "libcache", "logs"]
    faltando = [d for d in dirs if not (ROOT / d).is_dir()]
    add("Pasta do projeto", not faltando, "verde" if not faltando else "vermelho",
        "OK" if not faltando else f"falta: {', '.join(faltando)}")

    # 2. Rota de instalação (brew é só mac; universal = uv/jar na própria pasta)
    brew = shutil.which("brew") if sys.platform == "darwin" else None
    rota = "instalador universal (§17 F5): uv + venv + Zulu/JRE + freerouting.jar"
    extra = "" if brew else (" | brew ausente (ok — Rota B sem sudo)" if sys.platform == "darwin" else "")
    add("Rota de instalação", True, "verde", rota + extra)

    # 3. Python do venv
    venv_py = _py_venv()
    py_versao = run(f"{venv_py} --version | awk '{{print $2}}'") if venv_py.exists() else None
    ok_py = bool(py_versao) and py_versao.split(".") >= ["3", "12"]
    add("Python venv ≥3.12", ok_py, "verde" if ok_py else ("amarelo" if not venv_py.exists() else "vermelho"),
        py_versao or "venv ainda não criado")

    # 4. Java (Freerouting 2.5 exige classe 69 = Java 25) — local tools/ ou PATH
    java_out = None
    zulus = sorted(glob.glob(str(ROOT / "tools" / "zulu*")))
    for zulu in zulus:
        for java_bin in glob.glob(os.path.join(zulu, "**", "bin", "java"), recursive=True):
            java_out = run(f"'{java_bin}' -version 2>&1 | head -1")
            if java_out:
                break
        if java_out:
            break
    if not java_out and shutil.which("java"):
        java_out = run("java -version 2>&1 | head -1")
    ok_java = bool(java_out) and re_25(java_out)
    add("Java runtime (Zulu 25)", ok_java, "verde" if ok_java else "amarelo",
        java_out if java_out else "NÃO INSTALADO (tools/zulu* ou PATH)")

    # 5. KiCad + bibliotecas (descoberta universal — pcbforge.paths)
    sh = paths.kicad_shared()
    ver = None
    if sys.platform == "darwin" and sh:
        ver = run("defaults read /Applications/KiCad.app/Contents/Info.plist "
                  "CFBundleShortVersionString 2>/dev/null")
    add("KiCad", bool(sh), "verde" if sh else "amarelo",
        f"versão {ver} — {sh}" if sh else "NÃO INSTALADO (sem symbols/ + footprints/)")

    # 6. Bibliotecas KiCad (embutidas)
    faltam = [d for d in ("symbols", "footprints", "3dmodels")
              if not (sh and (sh / d).is_dir())]
    add("Bibliotecas KiCad", not faltam, "verde" if not faltam else "amarelo",
        str(sh) if not faltam else f"falta {', '.join(faltam)} — 1ª execução do app")

    # 7. Freerouting
    jar = ROOT / "tools" / "freerouting.jar"
    add("Freerouting JAR", jar.exists(), "verde" if jar.exists() else "vermelho",
        f"{jar.stat().st_size // (1024*1024)} MB" if jar.exists() else f"faltando {jar}")

    # 8. Pacotes do venv
    pacotes = ["kiutils", "kicad_sch_api", "easyeda2kicad", "matplotlib", "yaml", "click", "pytest"]
    res = []
    for pacote in pacotes:
        if not venv_py.exists():
            v = "pendente"
        else:
            v = run(f"{venv_py} -c 'import {pacote}'")
        res.append((pacote, "🟡" if v == "pendente" else ("🟢" if v is None else "🔴")))
    all_ok = all(s == "🟢" for _, s in res)
    add("Pacotes do venv", all_ok, "verde" if all_ok else "amarelo",
        "  ".join(f"{p}{s}" for p, s in res) if venv_py.exists() else "depende do venv")

    # 9. config/env.yaml
    cfg = ROOT / "pcbforge" / "config" / "env.yaml"
    add("config/env.yaml", cfg.exists(), "verde" if cfg.exists() else "vermelho",
        "OK" if cfg.exists() else "faltando")

    print(f"\n{'Item':<22} {'Estado':<9} Detalhe")
    print("-" * 72)
    for item, estado, detalhe, s in CHECKS:
        print(f"{item:<22} {estado:<9} {s} {detalhe}")
    n_vermelho = sum(1 for c in CHECKS if c[3] == "🔴")
    print("-" * 72)
    print(f"🔴 {n_vermelho} item(ns) bloqueador(es)")
    print("")
    print("Itens 🟡 são instaláveis pelo install.sh / install.ps1 (não bloqueiam).")
    return 0 if n_vermelho == 0 else 1


def re_25(saida: str) -> bool:
    """Java 25+ (Freerouting 2.5 abre .class 69 — Java 25; JRE forwards-compat)."""
    import re

    m = re.search(r'version "(\d+)\.', saida)
    return bool(m) and int(m.group(1)) >= 25


if __name__ == "__main__":
    sys.exit(main())

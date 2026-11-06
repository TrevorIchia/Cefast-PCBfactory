"""pcbforge.paths — raízes do projeto e do KiCad (F5 — instalador universal, M11).

Nenhum módulo do pipeline deve depender de caminho fixo de usuário: quem decide
é esta descoberta, nesta ordem —

  raiz do projeto:  env PCBFORGE_ROOT  >  parents[1] deste arquivo
  KiCad (SharedSupport equivalente, com symbols/ de footprints/ de 3dmodels/):
      env PCBFORGE_KICAD_DIR
      > macOS:      /Applications/KiCad.app/Contents/SharedSupport
      > Linux:      /usr/lib/kicad/share/kicad, /usr/share/kicad, /opt/kicad
      > Windows:    C:\\Program Files\\KiCad\\<versão>\\share\\kicad (e raiz)
"""
from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path


def root() -> Path:
    """Raiz do repositório PCBForge (a pasta que contém pcbforge/, boards/, …)."""
    env = os.environ.get("PCBFORGE_ROOT")
    if env and Path(env).is_dir():
        return Path(env).resolve()
    return Path(__file__).resolve().parents[1]


def libcache() -> Path:
    """Cache de peças baixadas (LCSC etc.) — <root>/libcache."""
    return root() / "libcache"


def _candidatos_shared() -> list[Path]:
    fora: list[Path] = []
    env = os.environ.get("PCBFORGE_KICAD_DIR")
    if env:
        fora.append(Path(env).expanduser())
    if sys.platform == "darwin":
        fora.append(Path("/Applications/KiCad.app/Contents/SharedSupport"))
    elif sys.platform.startswith("linux"):
        fora += [Path("/usr/lib/kicad/share/kicad"), Path("/usr/share/kicad"),
                 Path("/usr/lib/kicad"), Path("/opt/kicad/share/kicad")]
    elif sys.platform in ("win32", "cygwin"):
        base = Path("C:/Program Files/KiCad")
        if base.is_dir():
            for verdir in sorted(base.iterdir()):
                if verdir.is_dir():
                    fora += [verdir / "share" / "kicad", verdir]
    return fora


@lru_cache(maxsize=1)
def kicad_shared() -> Path | None:
    """Diretório que contém `symbols/` + `footprints/` (bibliotecas oficiais embutidas).

    Devolve None quando não achou — o chamador trata como needs_review
    (nunca inventa componente, §13.3).
    """
    for base in _candidatos_shared():
        if not base.is_dir():
            continue
        for d in (base, base / "share" / "kicad", base / "Contents" / "SharedSupport"):
            if (d / "symbols").is_dir() and (d / "footprints").is_dir():
                return d
    return None


@lru_cache(maxsize=1)
def kicad_cli() -> str | None:
    """kicad-cli do SO (erc/drc/gerbers/step/render) — descoberta por plataforma.

    Ordem: env PCBFORGE_KICAD_CLI > macOS (.app) > Windows (bin\\kicad-cli.exe
    da versão mais nova) > Linux (/usr/bin/kicad-cli) > PATH (which). None se
    não achou — o chamador trata como falta de ambiente (doctor/vermelho 🔴).
    """
    env = os.environ.get("PCBFORGE_KICAD_CLI")
    if env and Path(env).exists():
        return env
    if sys.platform == "darwin":
        c = Path("/Applications/KiCad.app/Contents/MacOS/kicad-cli")
        return str(c) if c.exists() else None
    if sys.platform in ("win32", "cygwin"):
        base = Path("C:/Program Files/KiCad")
        if base.is_dir():
            for verdir in sorted(base.iterdir(), reverse=True):
                c = verdir / "bin" / "kicad-cli.exe"
                if c.exists():
                    return str(c)
    else:  # linux e afins
        for c in ("/usr/bin/kicad-cli", "/usr/local/bin/kicad-cli"):
            if Path(c).exists():
                return c
    import shutil
    return shutil.which("kicad-cli")


def symbols_dir() -> Path | None:
    """`symbols/` das libs oficiais — sempre via kicad_shared() (nunca fixo)."""
    s = kicad_shared()
    return None if s is None else s / "symbols"


def footprints_dir() -> Path | None:
    """`footprints/` das libs oficiais (as .pretty aptas do censo)."""
    s = kicad_shared()
    return None if s is None else s / "footprints"


def plugins_dir() -> Path | None:
    """`scripting/plugins` equivalente por plataforma (ex.: InteractiveHtmlBom)."""
    s = kicad_shared()
    if s is None:
        return None
    for cand in (s / "scripting" / "plugins", s / "plugins", s / "python" / "scripting" / "plugins"):
        if cand.is_dir():
            return cand
    return None


def tmp_dir() -> Path:
    """Temporal DE CADA SO (Windows não tem /tmp)."""
    import tempfile
    return Path(tempfile.gettempdir())


@lru_cache(maxsize=1)
def ki_python() -> str | None:
    """Python EMBUTIDO do KiCad (tem o módulo pcbnew) — p/ pontes como dsn_bridge.

    Ordem: env PCBFORGE_KI_PY > macOS (Framework do .app, glob por versão)
    > Linux (/usr/lib/kicad/bin/python3) > Windows (bin\\python.exe da versão
    mais nova). None quando não achou — o chamador cai no fallback próprio
    (nunca crash: §9).
    """
    env = os.environ.get("PCBFORGE_KI_PY")
    if env and Path(env).exists():
        return env
    if sys.platform == "darwin":
        import glob

        hits = sorted(glob.glob("/Applications/KiCad.app/Contents/Frameworks/"
                                "Python.framework/Versions/*/bin/python3*"))
        return hits[-1] if hits else None
    if sys.platform.startswith("linux"):
        for c in ("/usr/lib/kicad/bin/python3", "/usr/bin/python3"):
            if Path(c).exists():
                return c
        return None
    if sys.platform in ("win32", "cygwin"):
        base = Path("C:/Program Files/KiCad")
        if base.is_dir():
            for verdir in sorted(base.iterdir(), reverse=True):
                exe = verdir / "bin" / "python.exe"
                if exe.exists():
                    return str(exe)
    return None

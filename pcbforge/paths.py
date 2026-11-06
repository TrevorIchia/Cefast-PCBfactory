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

"""Censo da biblioteca de footprints KiCad (F1 — limpa de componentes, M2).

Wrapper fino: a lógica mora em `pcbforge/parts/catalogo.py` (Mesma rotina usada
pelo runtime com fallback automático). Uso:

    .venv/bin/python --regenerar    # gera/troca pcbforge/config/catalogo.json
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pcbforge.parts import catalogo  # noqa: E402


def main() -> None:
    if "--regenerar" not in sys.argv and "--testar" not in sys.argv:
        print("uso: censo_footprints.py --regenerar | --testar")
        raise SystemExit(1)
    if "--testar" in sys.argv:
        cat = catalogo.carregar()
        print(len(cat), "footprints | amostra:")
        for k in ("LED_SMD:LED_0603_1608Metric", "Resistor_SMD:R_0603_1608Metric"):
            print(" ", k, cat.get(k))
        print("  MountingHole_3.2mm_M3:",
              [(k, v) for k, v in cat.items() if "MountingHole_3.2mm_M3" in k])
    else:
        meta = catalogo.gerar_catalogo()
        print(f"catalogo.json: {meta['total']} aptos ({meta['smd']} smd, {meta['tht']} tht)")


if __name__ == "__main__":
    main()

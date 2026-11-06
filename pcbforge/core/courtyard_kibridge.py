#!/usr/bin/env python3
"""courtyard_kibridge — roda DENTRO do Python do KiCad (tem pcbnew), F7.

Não importar do venv: este arquivo é executado como script pelo python do
próprio KiCad (mesmo padrão do routing/dsn_bridge.py).

Entrada:  argv[1] = pasta das bibliotecas (.pretty)
          argv[2:] = refs "lib:nome"
Saída:    UMA linha no stdout:  PCBFORGE_JSON {ref: [minx,miny,maxx,maxy] mm}
          (ref ausente/None ⇒ sem courtyard declarado — o chamador usa fallback)

Fonte da verdade: FOOTPRINT.GetCourtyard(F_CrtYd) — o MESMO parser do DRC do
KiCad ⇒ zero divergência entre o guard de placement e o DRC (F0 provou que o
kiutils dá falso-negativo em geometria de fórmula do .kicad_mod, ex. J2).
"""
import json
import sys

import pcbnew

NM = 1e6  # unidade interna do KiCad (nm) → mm


def main() -> int:
    base = sys.argv[1]
    saida: dict[str, list[float] | None] = {}
    for ref in sys.argv[2:]:
        try:
            lib, nome = ref.split(":", 1)
            fp = pcbnew.FootprintLoad(f"{base}/{lib}.pretty", nome)
            poly = fp.GetCourtyard(pcbnew.F_CrtYd) if fp is not None else None
            if poly is None:
                saida[ref] = None
                continue
            bb = poly.BBox()
            saida[ref] = [bb.GetLeft() / NM, bb.GetTop() / NM,
                          bb.GetRight() / NM, bb.GetBottom() / NM]
        except Exception:                                  # noqa: BLE001
            saida[ref] = None
    print("PCBFORGE_JSON " + json.dumps(saida))
    return 0


if __name__ == "__main__":
    sys.exit(main())

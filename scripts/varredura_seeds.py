"""Varre seeds testando o roteamento REAL de cada layout (F0-3).

Para cada seed: otimizar placement → gerar kicad_pcb com esse layout →
exportar DSN → cirurgia face-simples → Freerouting → contar unrouted.
Para na primeira seed com 0 unrouted.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

import yaml
from pcbforge.core import placement as pl
from pcbforge.core.validator import aplicar_default_espessura
from pcbforge.generator.pcb import aplicar_regras_projeto, gerar_pcb
from pcbforge.routing import facesimples, run as rt

ROOT = Path(__file__).resolve().parents[1]
NOME = "ex-attiny-isp-1l"
PASTA = ROOT / "boards" / NOME
OUT = PASTA / "outputs"
DIGI = OUT / f"{NOME}.dsn"
SES = OUT / "varredura.ses"

netlist = json.loads((PASTA / "design" / "netlist.json").read_text())
perfil = yaml.safe_load((PASTA / "design" / "board_profile.yaml").read_text())
aplicar_default_espessura(perfil)

log: list[str] = []
for seed in range(1, 21):
    layout, mm0, mm1 = pl.otimizar(netlist, perfil, seed=seed, iteracoes=600)
    cruz = pl.contar_cruzamentos(netlist, layout)
    conf = pl.contar_conflitos(pl.coords_pads(netlist, layout)[1])
    if cruz != 0 or conf != 0:
        print(f"seed {seed:2d}: descartada (cruz {cruz}, confl {conf})")
        continue
    gerar_pcb(netlist, perfil, PASTA / "kicad", NOME, layout=layout)
    aplicar_regras_projeto(PASTA / "kicad", NOME, perfil)
    rt.exportar_dsn(PASTA / "kicad" / f"{NOME}.kicad_pcb", DIGI, log)
    ok, _msg = facesimples.bloqueio_b_cu(DIGI)
    if not ok:
        print(f"seed {seed:2d}: FALHA cirurgia face simples"); continue
    resumo = rt.rotear(DIGI, SES, 120, log)
    print(f"seed {seed:2d}: MST {mm0:.0f}→{mm1:.0f}mm | unrouted={resumo.get('unrouted')} viol={resumo.get('violations')}")
    if resumo.get("unrouted", 1) == 0:
        print(f"\n✅ SEED VERDE: {seed} (salve DSN/SES e rode o build completo)")
        break
print(f"({time.time():.0f}s)")

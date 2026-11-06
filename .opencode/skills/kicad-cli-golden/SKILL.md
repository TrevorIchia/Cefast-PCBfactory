---
name: kicad-cli-golden
description: Use em chamadas kicad-cli (ERC, DRC, export Gerbers/excellon/STEP/BOM, renders) e em troubleshooting de regras/constraints do .kicad_pro. Ambiente local: KiCad 10.0.7 no macOS (Intel).
---

# kicad-cli-golden

## Ambiente local

- kicad-cli: `/Applications/KiCad.app/Contents/MacOS/kicad-cli` (KiCad **10.0.7** — Intel mac)
- Libs oficiais: path via `pcbforge/paths.py` (descoberta automática — NUNCA path fixo; mac/Linux/Windows)
- Python embutido para pcbnew (SWIG, deprecated desde KiCad 9 mas VIVO): `/Applications/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9` — usado por `dsn_bridge`/ççcourtyard bridge; se quebrar no futuro: fallback `kigadgets`

## Comandos usados no pipeline

```bash
kicad-cli sch erc --format json <proj>.kicad_sch
kicad-cli pcb drc --format json <proj>.kicad_pcb
kicad-cli pcb export gerbers --layers F.Cu,Edge_Cuts,… <proj>.kicad_pcb -o <dir>/
kicad-cli pcb drill … -o <dir>/
kicad-cli pcb export pos <proj>.kicad_pcb
kicad-cli pcb export step <proj>.kicad_pcb
kicad-cli sch export <svg|pdf>
```

## Armadilhas — relembrar sempre

1. **DRC reescreve `.kicad_pro`**: qualquer chamada ERC/DRC pode RASGAR as constraints do perfil (`board.design_settings.rules` é o bloco real; `board.rules` é fantasma). Ordem segura: aplicar regras ANTES da última chamada CLI e conferir sobrevivência depois (no cli.py, pós-DRC).
2. **kicad-cli v10 NÃO exporta Specctra DSN** (provado; notado na análise do circuitforge) → DSN via pcbnew embutido (`dsn_bridge`).
3. **Outlines viram cobre na export** — keepout fantasma no router (ver `freerouting-golden`).
4. **SES vazio (~252 bytes)** = router quase não rodou; conferir antes de assumir sucesso.
5. **Largura por corrente**: regras por net class aplicam na hora NO DSN (classes de roteador), não só no `.kicad_pro`; `routing.rules.aplicar` é o ponto único.

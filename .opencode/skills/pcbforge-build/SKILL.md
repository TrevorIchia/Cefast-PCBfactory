---
name: pcbforge-build
description: Use em QUALQUER comando do pipeline PCBForge (build, route, export, render, checklist, catalogo, brain, doctor), preflight de seeds e pytest. Regras duras de operação — workdir, comandos canônicos, gates e log.
---

# pcbforge-build

## Workdir é sagrado
Shell SEM workdir definido roda em `/Users/user` — **SEMPRE** passe `workdir=/Users/user/pcbforge` (ou `cd`).

## Comandos canônicos (venv dedicado, nunca python do sistema)

```bash
cd /Users/user/pcbforge
.venv/bin/python -m pcbforge.cli build <nome> --seed <N>     # golden semaforo usa --seed 12 (registro)
.venv/bin/python -m pytest tests/ -q                          # baseline 131/131 (30-10-2026)
.venv/bin/python -m pcbforge.cli checklist <nome>
```

## Gates antes de qualquer build

1. **Validation**: `validar_netlist` + `validar_perfil` zerados em `severidade=erro` (§13.1)
2. **Preflight de seeds de placement** (§4.3.2b): para seeds pretendidas, `otimizar(netlist, perfil, seed=s, iteracoes=do perfil)` → `contar_conflitos(coords_pads(netlist, layout)[1]) == 0` — seed com conflito GIRAR, nunca rotear por cima (cli.py:282)
3. **§13.2**: NUNCA exportar zip com ERC/DRC erro — bloqueador
4. **§13.3**: nunca inventar componente (needs_review existe para isso)
5. **Ponte 0Ω móvel** (§20.1): `pos_mm` de ponte é APENAS seed — nunca fixar ponte em disco
6. **Nome do projeto**: só `[A-Za-z0-9-]`

## Sempre que o build rodar
- `boards/<nome>/build.log` é obrigatório (§13.4)
- **Cronometrar** e registrar duração + seed + zips em §18 do Plano Mestre (ver skill `pcbforge-registrar`)
- Falhas: mostrar ref/causa exatos da falha (nunca "undefined") — ver `pcbforge-decisao`

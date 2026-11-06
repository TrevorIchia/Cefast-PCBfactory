# PARTS-SPEC — resolução de componentes (`parts/`, Plano Mestre §6/§14)

## Ordem de resolução (§6.1 — prioridade)

1. **Biblioteca oficial KiCad** — 1ª opção, offline (caminho descoberto por
   `pcbforge.paths.kicad_shared()`: mac SharedSupport, Linux `/usr/lib/kicad`,
   Windows `C:\Program Files\KiCad\<ver>\share\kicad` — ou env
   `PCBFORGE_KICAD_DIR`)
2. **Cache local** `libcache/`
3. **LCSC/JLCPCB** via **easyeda2kicad 1.0.1** — símbolo + footprint + 3D
   (STEP **e** WRL) gravados no cache
4. SnapEDA / UltraLibrarian — manual, com aviso (não automatizado v1)
5. Componente custom — só sob pedido explícito → `libcache/custom/`

## `catalogo.json` — a "limpa" de footprints aptos (F1/M2)

- Critério: pads **THT/SMD claros e numerados** + modelo 3D
  `${KICAD10_3DMODEL_DIR}/…step` **existente no disco**.
- **Exceção documentada**: `MountingHole` (furo puro, sem 3D por natureza).
- Censo atual: **7.546 aptos (3.618 SMD + 3.928 THT)** de ~15.4k do KiCad 10.
- Regenerar: `pcbforge catalogo --regenerar` (~1 min) ou
  `scripts/censo_footprints.py --regenerar`.
- Formato de registro: `{pads, smd_pads, tht_pads, tipo: smd|tht,
  puro_furo, step}` por ref `Lib:Footprint`.

## `resolve.py` — regras de decisão

1. `part_hint` = `C<digits>` → peça LCSC (`parts/lcsc.baixar_part`);
2. override por `value` (ex.: 0Ω → `Resistor_SMD:R_0402_1005Metric`... ver
   tabela `_OVERRIDES_VALUE` no código);
3. `DEFAULTS` por `type` (resistor → `Device:R` + `R_0603_1608Metric`, etc.);
4. tipo desconhecido → **`needs_review`**.

Guard universal: o footprint devolvido **tem de estar apto** no catálogo;
caso não seja, troca pela `melhor_alternativa` da mesma lib (família mais
parecida); sem alternativa → `needs_review`. **Nunca inventa componente
(§13.3)** — nem o brain, nem o resolver.

## `lcsc.baixar_part(c_id)` — LCSC completo

```python
{"symbol_ref": "LCSC:C8734",
 "footprint_ref": "LCSC:LQFP-48_L7.0-W7.0-P0.50-LS9.0-BL",
 "model3d": ".../libcache/lcsc/C8734.3dshapes/….step",
 "fonte": "lcsc" | "lcsc-cache",
 "estados": []}          # [] = sucesso
```

- Layout do cache: `libcache/lcsc/<C-id>.kicad_sym`, `<C-id>.pretty/*.kicad_mod`
  (caminho do `.wrl` já absoluto, reescrito pelo wrapper),
  `<C-id>.3dshapes/*.step|*.wrl`.
- **Idempotente/offline** (P04): artefatos presentes ⇒ sem rede.
- Estados de falha (§9): `cooldown` / `timeout` / `falha_baixa` / `api_falha`
  — devolvidos, nunca exceção estourando.
- Defesas WAF: intervalo mínimo entre requisições + cooldown global no 403.
- Evidência real: **C8734** (STM32F103C8T6) baixada com 3D; **C28100**
  (exemplo clássico) está **retirada da LCSC** — endpoint responde
  INEXISTENTE (não é bug do wrapper).

## Funções (estado v1, Plano Mestre §6.2)

| Função | Estado v1 |
|---|---|
| `pesquisar_part`/`resolver` | ✅ (defaults + override + catálogo) |
| `baixar_lcsc` (`baixar_part`) | ✅ (símbolo + footprint + STEP/WRL) |
| `propor_alternativas` (`alternativas`/`melhor_alternativa`) | ✅ (mesma lib/família) |
| `validar_part` (pinos símbolo ↔ footprint) | 🟡 próximo (P03) — v1 confia nos pins do netlist |
| `atualizar_cache_index` | 🟡 (cache index disco já é o layout real) |
| `adicionar_part_custom` | 🔴 v2 |

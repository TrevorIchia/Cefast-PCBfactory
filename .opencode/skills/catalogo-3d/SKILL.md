---
name: catalogo-3d
description: Use ao adicionar/resolver componente, footprint, biblioteca, 3D (.step), cadastro ou auditoria do catálogo PCBForge. Lei F14a: SEM 3D REAL NO DISCO, NÃO ENTRA.
---

# catalogo-3d

## Lei do catálogo (F14a, §19.2)

`apto()` = **pads reais + modelo `.step` VERIFICADO no disco** (`$(KICAD10_3DMODEL_DIR)/<lib>/<nome>.step` existe). Exceção única: MountingHole (não é montada). NADA no pipeline admite footprint sem 3D — o render nunca mente.

## Fontes permitidas (auditadas por case-insensitive + prefixo `${KICAD8_3RD_PARTY}`)

1. **Oficial KiCad embarcado** — 15.464 footprints scaneados
2. **`libcache/kicad-extra`** — `espressif/kicad-libraries` oficial: +34 peças com 3D (7.546 → **7.580 aptos**); ex.: binding do ESP32-C3-MINI-1 é `Espressif:ESP32-C3-MINI-1` (a oficial `RF_Module:...` NÃO tem 3D!)
3. **LCSC via easyeda2kicad** — `baixar_part` (WAF: intervalo 3s + cooldown 5min + cache; C28100 = peça RETIRADA é caso documentado)

## Operação

- Catálogo em `/Users/user/pcbforge/config/catalogo.json`; regen: `pcbforge catalogo --regenerar`
- Resolver (`parts/resolve.py`): `_OVERRIDES_VALUE` → defaults THT → inferência CI por pacote/pinos → `needs_review` (nunca inventa — §13.3)
- Vírgula decimal ("0,1 µF") já classificada ELETROLÍTICA por bug — fix com keywords cerâmicas (f10 atualizado)
- Toda peça nova entra `needs_review` até o usuário aprovar; sem `.step` em NENHUMA fonte ⇒ RECUSADA com mensagem clara ("footprint fantasma" é proibido)

## Anti-patterns
- Confiar que o `.step` "existe" sem procurar no disco (case diferente É inexistência)
- Footprint oficial sem 3D quando há variante de lib toda-extras APTA
- Editar `apto()` para "passar o caso" — se a peça não tem 3D, o catálogo é que recusa

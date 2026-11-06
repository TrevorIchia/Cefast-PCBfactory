# BOARD-PROFILE-SPEC — schema do `design/board_profile.yaml` (Plano Mestre §4/§14)

Revisado na GUI (§13.2): um PUT inválido **não salva**. Defaults v1 do
validator (`core/validator.py::aplicar_default_espessura`): `thickness_mm: 1.6`,
`copper_oz: 1.0`, `color: green`, `silkscreen: white` quando ausentes.

## Exemplo real (golden I01 completo)

```yaml
name: ex-led-blink-1l
stackup:
  layers: 1            # FACE SIMPLES — teste da regra §4.3
  board_material: FR4
  copper_oz: 1.0
  thickness_mm: 1.6
  color: green
  silkscreen: white
gold_fingers: false
size_mm: {w: 50, h: 30}
outline_shape: retângulo
mounting: {diameter_mm: 3.2, corners: 4, margin: 3}
min_trace_mm: 0.25
min_clearance_mm: 0.25
min_via_mm: 0.5
high_current_traces: []
autoroute: {timeout_s: 600}
assembly_jlcpcb: false
thermal_reliefs: true
notes: golden I01 — primeiro teste completo do pipeline
```

## Campos

| Campo | Valores | Notas |
|---|---|---|
| `name` | string | nome do projeto |
| `stackup.layers` | 1, 2, 4, 6, 8 | nº de camadas de cobre; **1 = face simples** |
| `stackup.board_material` | FR4 / FR4-TG170 / Alu / flex | |
| `stackup.thickness_mm` | 0.6 – 2.0 | default 1.6 |
| `stackup.color` | green/red/blue/white/black/yellow | fora da paleta JLC → warning + sugestão (R06) |
| `stackup.silkscreen` | white/black | |
| `gold_fingers` | bool | dedos de conector |
| `size_mm` | `{w, h}` mm | dimensions do outline |
| `outline_shape` | retângulo / círculo / DXF | v1: retângulo completo |
| `mounting` | `{diameter_mm, corners, margin}` | `corners` aceita 0/1/2/4 |
| `min_trace_mm` | default 0.25 | herdado ao DSN (250/250 no `.kicad_pro`/netclass) |
| `min_clearance_mm` | default 0.25 | idem |
| `min_via_mm` | default 0.5 | |
| `high_current_traces` | `[{net, A}]` | largura aumentada automática por corrente |
| `autoroute` | `{timeout_s, max_vias?, layers_allowed?}` | regras p/ Freerouting |
| `assembly_jlcpcb` | bool | BOM/centroid no formato SMT da JLC |
| `budget_usd` | número opcional | teto de custo |
| `thermal_reliefs` | bool | pads térmicos em nets de potência |
| `notes` | string | livre |

## Códigos de erro do perfil (U06–U08, R05/R06)

| Código | Nível | Significado |
|---|---|---|
| `CAMADAS_INVALIDAS` | erro | `layers` fora de 1..8 |
| `COR_NAO_PADRAO` | warning | cor fora da paleta JLC (sugestão vem na mensagem) |
| `SILK_NAO_PADRAO` | warning | silk ≠ white/black |
| `MOUNTING_INVALIDO` | erro | `corners` fora de 0/1/2/4 |
| `MULTICAMADA_X_GOLDFINGERS` | erro | face simples não suporta gold_fingers (R05) |
| `VIA_EM_FACESIMPLES` | erro | pedir rotear 2 camadas num perfil de 1 (U07) |

## Regras de FACE SIMPLES (§4.3 — v1 apóia 1–2 camadas)

1. **Sem vias** — todo cruzamento de trilha precisa de: **(a)** ponte 0Ω,
   **(b)** reorganização (menu de seeds §4.3.2b), ou **(c)** migração para
   2 camadas. **O menu aparece e você decide** — o pipeline nunca decide sozinho.
2. cruzamento sem solução → **detectado antes** do Freerouting (penalidade no
   custo do placement, 120 mm/cruz) e conversado.
3. margem de borda: **2,0 mm** (§7.1.6) entre pad/trilha e outline.
4. componentes montados em face BOTTOM rejeitados com aviso (nada roda em
   cobre único BOTTOM); MountingHole é furo puro apto (PARTS-SPEC).

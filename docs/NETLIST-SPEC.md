# NETLIST-SPEC — schema do `design/netlist.json` (Plano Mestre §5.2/§14)

Arquivo único que descreve o circuito em formato neutro. O `brain/` gera uma
**proposta**; o usuário revisa linha a linha (§13.1) antes de gerar KiCad.
`symbol_ref`/`footprint_ref` **nunca são digitados à mão** — vêm do resolver
apto (§6, `docs/PARTS-SPEC.md`).

## Schema raiz

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `_comentario` | string | não | certeza: "REVISAR antes de gerar (§13.1)" |
| `version` | "1.0" | ✔ | versão do schema |
| `metadata` | obj | ✔ | `{name, created_by, description, created_at}` (+ `gerado_por_cb`, `pedido` quando veio do brain) |
| `board_profile_ref` | string | ✔ | caminho/inline do perfil (`exemplo-inline`, `../design/board_profile.yaml`) |
| `components` | lista | ✔ | ≥ 1 componente (senão erro `U00`) |
| `connections` | lista | ✔ | cada `{a, b, net_name}` |
| `rails` | lista | — | `[{net: "VBUS", voltage: 5.0, current: 0.02}]` |
| `constraints` | lista/dict | — | keepout/height/thermal (v1: geralmente `[]`) |

## `components[*]`

| Campo | Descrição |
|---|---|
| `ref` | `R1`, `C3`, `U2`… `A-Z` + dígitos; **duplicado → erro** (U02) |
| `type` | `resistor`, `capacitor`, `capacitor_polarizado`, `indutor`, `led`, `diodo`, `conector`, `ci`, `jumper`, `resistor_0r`, `montadora`… |
| `value` | `10k`, `100nF`, `ATtiny2313-20S`, `2p VBUS/GND` |
| `symbol_ref` / `footprint_ref` | `Lib:Nome` — **só do resolver/LCSC** (§13.3) |
| `source` | `kicad-library` / `lcsc` / `lcsc-cache` / `override` / `needs_review` |
| `part_hint` | opcional: MPN ou C-code LCSC se o usuário especificou |
| `pins` | opcional (lido da biblioteca): `[{number, name, dir}]` |
| `papel` / `needs_review` | opcional: função no circuito / flag do brain ou resolver |

## `connections[*]`

```json
{"a": {"ref": "J1", "pin": "1"}, "b": {"ref": "J2", "pin": "2"}, "net_name": "VCC"}
```

- `pin` é **string** (compatível com pinos nomeados);
- conexão com endpoint não identificável (`"?…"` / sem `ref` válido) é
  **descartada pelo brain** — nunca inventada.

## Códigos de erro (validator — `core/validator.py`, testes U01–U08)

| Código | Nível | Significado |
|---|---|---|
| `U00` | erro | netlist sem componentes (U01 no plano: ≠0 componentes) |
| `REF_DUPLICADO` | erro | ref aparece N× (U02) |
| `PIN_INEXISTENTE` | erro | conexão para ref desconhecido ou pino não existe (U03) |
| `RAIL_SEM_FONTE` | erro | rail declarada sem ≥1 conexão (U04) |
| `PART_SEM_FOOTPRINT` | warning | componente sem `footprint_ref` (U05) |

A resposta é **lista de `{codigo, severidade, mensagem}`** (nunca crash, §9).
Na GUI (§13.1) um PUT com problema é **não salvo** — painel mostra as msgs.
Fluxo completo do brain e o formato de revisão: `docs/WORKFLOW-QUOTE.md`.

## Exemplo real (goldens/examples)

`examples/ex-attiny-isp-1l/netlist.json`: U1 ATtiny2313 SOIC-20W + J1/J2
headers 2×3 + R's 0603 + D/Zener — 12 nets, face simples, ISP. Consulte
também `boards/ex-led-blink-1l/design/netlist.json` (mínimo: J1 VBUS/GND →
R1 330Ω → D1 RED).

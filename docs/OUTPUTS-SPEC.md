# OUTPUTS-SPEC — artefatos gerados por build (Plano Mestre §8/§14, testes X01–X08)

Tudo vive dentro de `boards/<nome>/` (§3.3). O build só exporta quando
**ERC = 0 e DRC = 0 bloqueadores** (regra de ouro §13.1) — zip existente é
sempre de uma rodada verde (relatórios congelados em `verify/`).

## Árvore

```
boards/ex-led-blink-1l/
├── design/
│   ├── request.md                    # pedido original em linguagem natural
│   ├── netlist.json                  # NETLIST-SPEC.md (§13.1)
│   └── board_profile.yaml            # BOARD-PROFILE-SPEC.md (§13.2)
├── kicad/
│   ├── <nome>.kicad_sch              # esquemático gerado (G01)
│   ├── <nome>.kicad_pcb              # PCB roteada pós-SES (G02)
│   ├── <nome>.kicad_pro              # constraints reais (rules + netclass)
│   └── <nome>.kicad_prl              # prefs locais do KiCad
├── verify/
│   ├── erc_report.json               # JSON do kicad-cli (V01)
│   └── drc_report.json               # violações + unconnected_items (V02–V04)
├── outputs/
│   ├── gerbers/                      # um arquivo gerber por camada + drill + job
│   ├── <nome>-v<N>-<N>c-<YYYYMMDD>.zip   # o zip que vai pra fábrica (X01/X02)
│   ├── bom.csv                       # X03/X04
│   ├── centroid.csv                  # X05 (pick&place)
│   ├── board.step                    # X06 (3D mecânico, mm)
│   ├── <nome>-esquematico.pdf        # PDF do esquemático
│   ├── <nome>.dsn / <nome>.ses       # Specctra (Freerouting ↔ KiCad)
│   └── renders/                      # top.png, bottom.png, iso.png
└── build.log                         # cronologia completa (§13.4)
```

## Gerbers dentro do zip (X01 — 1 camada)

`<nome>-F_Cu.gtl`, `<nome>-F_Mask.gts`, `<nome>-F_Silkscreen.gto`,
`<nome>-Edge_Cuts.gm1`, `<nome>.drl` (Excellon, mm absoluto) e
`<nome>.gbrjob`. Em 2 camadas somam `-B_Cu.gbl`, `-B_Mask.gbs`,
`-B_Silkscreen.gbo`. Integridade conferida por `zipfile.testzip` (V-plane).

## Nome do zip (X02/X07)

`<nome-higienizado>-v<N>-<N>c-<ano><mês><dia>.zip` — espaços viram hífen
("minha placa 1" → `minha-placa-1-v1-2c-20261028.zip`). Também existe o
`<nome>-v1-1c-jlc.zip` (variante JLC de upload único quando
`assembly_jlcpcb: true`).

## BOM (`bom.csv` — X03/X04)

Colunas **exatas**: `Ref, Qty, Value, Footprint, LCSC C-code, MPN,
Description`. Componentes idênticos agregam: 4 resistores 10k viram uma linha
`R1,R2,R3,R4 | 4 | 10k | …`.

## Centroid (`centroid.csv` — X05)

Uma linha por componente com X/Y (mm), `rot` e `side` (`top`/`bottom`,
preenchidos) — pronto para o montador SMT.

## STEP (X06) / renders

`board.step` em **mm**, com os modelos 3D dos footprints posicionados;
`renders/*.png` renderizados pelo KiCad (top/bottom/iso, 1200 px).

## Determinismo/export idempotente (X08)

Exportar duas vezes produz bytes idênticos. O pipeline nunca exporta com
bloqueadores (o build **falha antes**, §13.1) — "silk cosmético" (warning)
pode passar, violação erro não.

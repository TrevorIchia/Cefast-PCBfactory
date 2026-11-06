# PCBForge

De **linguagem natural** a **placa fabricável** — pipeline 100% open source:
descreva o circuito por texto, o motor IA (`OpenCode CLI` + `GLM 5.3 Flash`)
propõe a netlist **sem inventar componente**, o pipeline gera esquemático +
PCB, otimiza o placement (MST + anti-cruzamento), roteia com Freerouting,
verifica (ERC/DRC/courtyard/catálogo) e entrega **Gerbers/BOM/centroid/STEP**
prontos para JLCPCB.

> Fonte de verdade de requisitos/fases/testes:
> `/Users/user/.opencode/plan/PCBForge-PLANO-MESTRE.md`. Estes docs cobrem
> operação e schemas; as regras vivas (§13.1/13.2/13.3/13.4, §4.3, §7.1.6,
> §13.8) estão referenciadas em cada spec.

## Instalação universal (um comando, sem sudo)

```bash
./install.sh                                   # macOS / Linux
powershell -ExecutionPolicy ByPass -File install.ps1    # Windows
```

Idempotente: pula artefatos presentes, instala os que faltam e termina com
`doctor` em **0 🔴**. Baixa: uv → Python 3.12 venv → deps (`requirements.txt`
pinned) → OpenCode CLI → Java Zulu 25 → KiCad (~4,8 GB com bibliotecas
embutidas) → freerouting.jar → `catalogo.json` (censo). Nesta máquina o
requisito de sudo passou longe: nada sai da pasta do projeto além dos
instaladores no `$HOME` (Rota B, §2.3/§18).

## Primeira placa em 5 minutos

```bash
source scripts/env.sh
python -m pcbforge.cli doctor                            # ambiente ok?
python -m pcbforge.cli brain "placa blink: led + resistor + conector 5V, \
    face simples"                                        # prévia + perguntas honra
python -m pcbforge.cli serve                             # painel web (revisão + build)
```

No painel: revisar netlist/perfil → escolher seed → **▶ Build** → checklist
✅ → baixar zip → JLCPCB. Receita completa passo a passo:
`docs/WORKFLOW-QUOTE.md`.

## CLI (Plano Mestre §11, estado v1)

| Comando | O que faz | Estado |
|---|---|---|
| `doctor` | diagnóstico do ambiente (universal, cross-plataforma) | ✅ M0 |
| `new <nome> --camadas N` | cria skeleton do projeto | ✅ M1 |
| `catalogo [--regenerar]` | censo dos footprints aptos | ✅ F1/M2 |
| `build <nome> --seed N` | netlist→KiCad→placement→roteamento→export (falha antes de exportar se ERC/DRC ≠ 0) | ✅ M3–M5 |
| `checklist <nome>` | checklist pré-fabricação (V-plane) | ✅ F2/M6 |
| `brain "<pedido>" [--criar nome]` | linguagem natural → netlist proposta | ✅ F4/M10 |
| `serve` | painel web FastAPI | ✅ F3/M9 |
| `route` / `export` / `render` / `parts` standalone | partição do build | 🟡 v2 (build cobre tudo) |

## Specs

| Doc | Conteúdo |
|---|---|
| [NETLIST-SPEC](NETLIST-SPEC.md) | schema do netlist.json + códigos de erro do validator |
| [BOARD-PROFILE-SPEC](BOARD-PROFILE-SPEC.md) | schema YAML + defaults + regras de face simples |
| [PARTS-SPEC](PARTS-SPEC.md) | ordem de resolução, catálogo (7.546 aptos), LCSC/libcache |
| [OUTPUTS-SPEC](OUTPUTS-SPEC.md) | cada artefato de `boards/<nome>/` |
| [GUI-SPEC](GUI-SPEC.md) | painel web: endpoints e garantias §13 |
| [WORKFLOW-QUOTE](WORKFLOW-QUOTE.md) | receita de bolo do pedido à fábrica |

## Regra de ouro & "conversas obrigatórias"

- **nunca exporta com ERC/DRC ≠ 0** (silk cosmético warning pode; erro nunca);
- cruzamento de trilha em face simples → **menu §4.3**: 0Ω / reorganizar
  (seed) / p/ 2 camadas — **sua decisão**;
- componente inacessível → `needs_review`, nunca inventado (§13.3);
- cada build deixar `build.log` completo (§13.4) — fonte de verdade dos
  relatórios: `boards/<nome>/verify/*.json`.

## Estado honesto (31-10-2026 — §18 do plano, F14a–F14c)

- **131 testes verdes** (126 na F13/F14a → **131** na F14c, com o cap global
  de pontes e fixes do gerador);
- **F14c FECHADA (31-10, checklist 6/6 + zip, 84s — critério §19.4)**: golden
  "semáforo de maquete" fabricável — U1 = ESP32-C3-MINI-1 (remap §20.3
  aprovado, straps GPIO8/9 evitados), **2 camadas** (decisão §4.3.1(c) do
  usuário após testes empíricos: roteamento 1L preso por capacidade
  física — unrouted 11–21 fixo), `semaforo-v1-2c-20261031.zip` com
  unrouted 0 / violações 0 / **score 1000** / ERC 0 / DRC 0 bloqueadores
  (build seed 19, 2 tentativas, court-dependente-de-rotação entra no
  retry-por-seed do loop §4.3.2b);
- **correções de raiz F14c** (provas no §18/§20 do plano): ângulo do token
  `pad` do `.kicad_pcb` é ABSOLUTO (bisseção + golden do pcbnew;
  violações pré-rota 44→0); `fp_text reference "REF**"` de libs extras
  vence o property no GetReference → normalização na importação; **cap de
  pontes é GLOBAL** (contar pontes persistidas — 9 herdadas > cap 6 no
  build 08; `core/ponte.py` + `unbridge_f14c.py` para reversão por
  decisão de camadas);
- **snapshot Freerouting 20261027 no pipeline** (backup 2.5.0 `.bak`):
  passes single-threaded = determinismo melhor, score 1000 no 2L; stop
  "stagnation" do issue #1031 ainda presente — marginais em 1L, mas
  ponta-certa do roteamento real. **Spike §19.6 `freeroute` PyPI
  DEMITIDO no vivo**: lê resolução DSN como 1 u = 1 µm (KiCad 0,1 µm) →
  SES 10× errado; veredito no §19.6.
- **107 testes verdes** (62 → 74 na F7 → 80 com o fix de outlines → 89 com
  `fixo` (4) + matriz v2 (5) → 102 com ângulos B1 + regras do roteador (6) +
  alternates (2) → 107 com a correção do detector de ângulos (5 casos de
  regressão dos falsos positivos) → 111 com clamp×fixo (1), furos-keepout
  (1), pad-girado (1) e estrela-T (1) + 2 do sanduíche → **114** com o fix
  do `Crystal_GND24` (3, abaixo);
- **matriz v2: 8/8 placas FABRICÁVEIS com zip (28-10 23:13 — FECHADA)** —
  I01 (led), 555 (46s), LM358 (39s), I03 attiny (44s), NE555 (32s),
  sanduíche (44s), **STM32 (67s)** e **shift595 (55s em 100×70, após 7
  rodadas §4.3.1**: tamanho 80→100×70 pelo usuário, ponte R9 0Ω no SHCP
  (decisão (a) do menu), âncora J1×courtyard-H1 resolvida com
  `mounting.margin 3→2.5` preservando as seeds — lição: **mudança de
  âncora muda as seeds do annealing e desloca as presas (whack-a-mole);
  ajustar o que NÃO muda as seeds primeiro**);
- **GUI no fluxo do PRODUTO (F9)**: abre no cartão "Seu pedido (§5.1)"
  — pedido → prévia (brain) → aprovação cria projeto com netlist +
  perfil de uma vez (`/api/brain/criar`); validado ao vivo com
  `boards/teste-gui-1`; `/seeds` protegido (422 sem componentes);
- **F13 (29-10)**: semáforo de maquete parou em peças vazias (ESP32/
  AMS1117 sem footprint) — todas as causas mortas no PROGRAMA:
  override `esp32` → footprint APTO com 3D; pacotes SOT-223/SOT-23/
  TO-92 na inferência; `_busca_simbolo` case-insensitive por prefixo;
  `PART_SEM_FOOTPRINT` = ERRO quando symbol também vazio; guard no
  `pads_do_footprint` (ValueError → erro legível, nunca crash);
  **gate pré-build** no `POST /build` (validação + catálogo, 422
  nomeando refs); **F14a**: lib oficial Espressif instalada em
  `libcache/kicad-extra` (+34 componentes com 3D auditado: 7580
  aptos); regeneração programática do design do `semaforo` (validator
  e catálogo 100% verdes). 126/126 testes. **§19 do plano**: backlog
  das 20 queixas de usuários EDA + regra "sem 3D não entra" + repos
  nicho avaliados;
- **bug upstream #2 morto no gerador (Crystal_GND24, 28-10 ~07:15)**:
  kicad-sch-api desloca a chave `private` das propriedades KLC da lib —
  `(property private "KLC_S3.3" "nota")` vira
  `(property "private" "KLC_S3.3" nota-solta-sem-aspas)` e o parser do
  KiCad rejeita o ARQUIVO INTEIRO. Prova por bissecção: lib_symbols vazio
  lê (rc 0); isolado por símbolo apontou Crystal_GND24 (rc 3); dentro
  dele, o 6º filho = 1ª propriedade private; LM358 + esse bloco = rc 3
  (tóxico em qualquer arquivo). São notas de documentação (sem função
  elétrica) ⇒ fix `_fixar_properties_private` (remoção pós-save, padrão
  `_fixar_alternates`); 3 testes. Depois do fix: sch do STM32 lê, ERC 0.
- **courtyards × furos e âncoras (regra A3/A7 fechada em 28-10)**: (i)
  `_clamp_borda` e `_fora_da_borda` NÃO move componente `fixo` (sanduíche:
  J1 4.0→5.045 em silêncio); (ii) furos M3 (courtyard ±3.49mm) entram só no
  gerador — agora `_caixas_furos` + passe de desencalhe no `otimizar`
  (sanduíche H1×R1); (iii) mesma família no STM32: headers fixos @y=8
  invadiam furos (courtyard 1x04 desce 9.4mm) ⇒ âncoras y→10 e J1 y→24
  (J1×J2 @y=20 sobrepunham 1.25mm). **Lição: âncora nova ⇒ re-verificar os
  courtyards dos 3 footprints fixos + furos ANTES do build.**
- **3ª rodada de diretrizes do usuário implementada (28-10-2026, ~05:50)**:
  (i) **clearance do ROUTEADOR separado do mínimo de fabricação** — o KiCad
  não exporta clearance cobre→borda pro DSN (issue #558 do Freerouting) e o
  router encosta no mínimo em todo lugar; agora `rules.py` regrava o DSN com
  `clearance_roteador_mm` (default = min_clearance + 0,05 ⇒ 0,30mm; o mínimo
  segue no DRC como gate). Fundamentos: JLCPCB "pad→trilha mín 0,20mm, more
  whenever possible"; AllPCB "margem além do mínimo"; Auckland/Altium
  0,5mm geral. (ii) **B2 largura por corrente**: classe própria no DSN com
  width = max(min_trace, 1mm/A) (NXP AN3962 conservador; JLCPCB "15+ mil
  power") p/ nets do perfil `high_current_traces` (fallback: rails ≥0,3A);
  (iii) **B1 cantos aplicada**: medição nos goldens provou que o Freerouting
  2.5.0 emite 12–16 quinas RETAS por placa (grade de roteamento) ⇒ gate duro
  bloquearia tudo. Política: agudo (<90° interior) = BLOQUEIO (acid trap
  real, NextPCB "under or AT 90°" / Altium DFM / e-e) e quina reta =
  CHANFRO automático pós-SES em 2×45° (`routing/angulos.py`, cateto 0,12mm,
  DRC logo em seguida valida o chanfro). **Bug do 1º detector (28-10,
  apanhado na 2ª rodada de builds)**: media o ângulo cru entre as direções
  start→end — que depende da orientação de escrita de cada segmento —
  gerando 6–13 falsos "agudos 135°/180°" por placa (dobra 45° com fio
  invertido; 2 fios em lados opostos do mesmo pad). Correção: viragem =
  180° − ângulo entre vetores "away" (p → outra ponta), independente de
  orientação; e **pads/vias são TERMINAIS** (conexão, não quina): ficam de
  fora do chanfro (trim desconectaria o terminal) e do gate de agudos.
  Knob `clearance_roteador_mm: 0.25` aplicado no I03 e shift595: 0,30
  regrediu os dois (corredores de 1 camada congestionada medidos);
- **bug upstream morto no gerador**: kicad-sch-api serializa
  `(alternate NAME ...)` SEM aspas — o parser do KiCad rejeita e o
  kicad-cli morre com "Houve uma falha ao ler o esquemático" (prova:
  STM32F103C8Tx, 36 alternates). Fix: `_fixar_alternates` re-quota após o
  save; 2 testes. Ver também o bug #2 (propriedades `private`, acima).
- **buraco do §13 fechado na prática**: o validador U01–U08 NÃO pega
  símbolo inexistente (a falha só explodiu no build: `Sensor_Temperature:
  LM75` não existe — o certo é **LM75B**, pins 1=SDA…8=+Vs conferidos na
  lib). Pendência P-N: validar symbol_ref/footprint_ref contra as libs
  ANTES do build;
- **Golden I03 (ATtiny ISP, 1 camada) ✅ fabricável de novo** — raiz das 7
  falhas de seed MEDIDA (não azar): U1 é SOIC-20W (pitch 1,27mm; vão entre
  pads ~0,67mm NÃO cabe trilha 0,18 + 2×0,25 = 0,68mm ⇒ escape só em
  fanout pra fora) e o J2 (ISP 2×3) estava SENTADO sobre o corredor de
  escape da coluna direita (a 2,0mm dos pads do U1, vão de ~0,7mm cabia
  1 trilha só p/ 3 nets). Fix conforme diretriz do usuário (regra **B6**,
  JLCPCB: "pad-to-pad < 0,5mm → não rotear entre os pads; contornar por
  fora" + Microchip AN18.15): J2 ancorado na borda de cima com
  `"fixo": true, "pos_mm": [47.0, 4.0]` → **unrouted=0, score 1000 na 1ª
  tentativa, ERC 0, DRC 0 bloqueadores, zip em 41s**;
- **feature `fixo` no netlist** (pré-requisito das regras A3/A7):
  `"fixo": true` + `pos_mm` = componente ANCORADO — o otimizador de
  placement não troca, não gira e não move (nem no passe final de
  sobreposições: desencalhe só move não-fixos). 4 testes
  (`tests/unit/test_placement_fixo.py`) incluindo regressão (sem a flag,
  comportamento antigo);
- **§4.3.2b agora cobre o placement INICIAL**: seed com sobreposição não
  aborta o build — gira pro próximo seed (antes abortava na 1ª; morto
  também o bug do `{n_conf}` literal no f-string);
- **regra B6 aplicada**, regra **A7 nova** (BTB/sanduíche): header de
  empilhamento com posição FIXA casada com a placa par + keepout de altura
  na zona de acasalamento (Soulin/Samtec: erro de altura não se conserta
  trocando part number);
- **matriz de testes v2** (pedido do usuário: variar os escopos): 5 placas
  novas em `boards/`, netlists+perfis validados 0/0, testes MV01–MV05
  (`tests/unit/test_matriz_v2.py`): #1 ex-lm358-amp-1l (THT puro, 1c, DIP-8);
  #2 ex-shift595-8led-1l (THT, 1c, DIP-16 + 8 LEDs); #3 ex-ne555-misto-2l
  (misto THT+SMD, 2c); #4 ex-shield-sanduiche-2l (sanduíche: headers 2x03/
  2x04 de empilhamento FIXOS, LM75 I2C, VCC/GND 0,5A); #5 ex-stm32-lqfp48-2l
  (LQFP-48 pitch 0,5mm, 2c, min_trace 0,18/clearance 0,2 — stress de escape
  B6). Todos os conectores `fixo:true` na borda (A3/A7);
- **"placa sanduíche" (definição por pesquisa)** = placas EMPILHADAS
  conectadas por board-to-board (estilo shield Arduino) — NÃO misto THT+SMD
  (isso é a #3) e NÃO componentes nas 2 caras: componentes na face BOTTOM
  não é suportado no v1 (placement não tem lado no estado) ⇒ fila F9;
- **F7 fechada**: courtyard via pcbnew (mesmo parser do DRC) — o falso-negativo
  do J2 (I03) acabou; rebuild do I03 re-verde (seed 6 no loop §4.3.2b), DRC
  com 0 `courtyards_overlap` checados pelo próprio KiCad;
- **Golden I04 (NE555 astável THT, 1 camada) ✅ fabricável** — brain (GLM) →
  revisão §13.1 → placement → roteamento → Gerbers zip. O brain perguntou
  U1.4 (RESET) em vez de inventar (§13.3); a revisão §13.1 unificou THR/
  THR_TRIG em OSC (o generator resolve net por nome) e adicionou U1.4→VCC;
- **bug sério pego e morto (root cause provado por experimento)**: o KiCad
  10.0.7 exporta courtyard/silks como `(outline (polygon signal 0 ...))` no
  DSN; o Freerouting 2.5.0 lê como keepout em camada de COBRE → nets ficam
  impossíveis e o router declara "0 unrouted, score 1000" com a net em ilhas
  (classe do bug "premature routing-complete detection", corrigido na v2.2.4
  e regredido na 2.5.0 — release mais nova). Fix: `routing/outlines.py`
  RECLASSIFICA a classe `signal`→`silk` dentro de cada `(outline ...)` —
  o outline CONTINUA no DSN (a "imagem" da placa segue visível p/ inspeção
  manual) e o Freerouting para de tratá-lo como keepout de cobre. Provas
  (mesmo DSN): original → 3 ilhas GND; sem outlines (run c) → 6/6 pins
  conectados; signal→silk (run E) → idêntico ao run c no roteamento.
  Keepouts reais dos furos M3 ficam — são `(keepout ...)` explícitos;
- **verificação dura pós-SES** (`routing/verifica_ses.py`): cada net precisa
  virar 1 grupo de cobre (pads pcbnew + fios do SES) ANTES de aplicar —
  qualquer mentira do router vira retry de seed (§4.3.2b), não DRC no fim;
- stdout do Freerouting persistido em `outputs/*.frlog` (§13.5);
- bug latente da F5 morto: `TEMPLATE_PRO` com caminho dobrado explodia só em
  projeto NOVO; agora via `paths.root()` (+ `FOOTPRINTS_DIR` dinâmico);
- **install.ps1** escrito; prova executável exige máquina Windows;
- Freerouting 2.5 não é determinístico multi-thread (documentado) ⇒
  mitigado com loop de tentativas (placement por seed) + DRC no loop +
  verificação dura do SES;
- fila pós-v1: I02 (2 camadas), ps1-Windows, P03, bom-interativo, conferir_3d,
  R01/R04; alternativa futura sem JVM anotada: `freeroute` (PyPI, Python
  puro) — hoje menos preciso em clearance;
- **F8 (fila pós-v1) — catálogo de regras de design (pesquisa 28-10-2026;
  origem: 2 achados do usuário revisando o I04 em 3D)**: (A1) THT 1 camada =
  cobre no LADO DO SOLDA (B.Cu), componentes em F — hoje o pipeline roteia em
  F.Cu (mesmo lado do corpo; JLCPCB/fórum KiCad: não passa em wave solder);
  (A3) bornier/conector NA BORDA com entrada de fio pra fora + corredor
  livre (RAYPCB "assembly access" — no I04 o J1 ficou enterrado); (A2)
  componentes ≥5mm da borda, exceto conectores (AllPCB); (A4) axiais THT
  orientação uniforme (AllPCB); (A5) LEDs/botões de painel perto da borda;
  (B1) cantos 45°, nunca agudo — **IMPLEMENTADO (28-10-2026)**: medição
  provou que o Freerouting emite 12–16 quinas retas/placa ⇒ agudo (<90°
  interior) = bloqueio e quina reta = chanfro automático 2×45° pós-SES
  (`routing/angulos.py`; acid trap: JLCPCB/NextPCB; efeito SI é mito <GHz
  segundo Altium, o motivo real é DFM); (B2) largura por corrente IPC-2221
  (10mil/0,25mm ≈ 1A externo 1oz ΔT10°C; NXP: 1mm/A) — campo `corrente_A`
  no netlist → net class no DSN; (B3) clearance por tensão IPC-2221 Tab.
  6-1 externo sem coating: ≤30V→0,1mm; 31–150V→0,6mm; 151–300V→1,25mm;
  301–500V→2,5mm; >500V→+0,005mm/V — por PAR de nets (ΔV) → net class;
  (B4) cobre→borda ≥0,5mm e furo→borda ≥0,5mm (v-score: 1,0mm) no DRC
  (IPC-2221 + PCBWay); (B5) furo-a-furo ≥0,25mm edge-to-edge (Eurocircuits/
  TTM); (C1) annular ring ≥0,15mm classe 2 (Altium/APTPCB); (C2) teardrops
  nativos do KiCad pós-import SES (Altium); (D1) thermal relief em pad THT
  com pour: 4 spokes, spoke ≥0,2mm, gap ≥0,25mm (IPC-2221B §9.1.4, JLCPCB,
  AtlasPCB); (D2) pour de GND no lado do cobre, opcional em 1c; (E1–E3)
  silkscreen: refdes por componente, texto ≥0,8mm (KLC: 1,0mm), traço
  ≥0,15mm, polaridade/pin1 VISÍVEL pós-montagem e nunca sobre pad,
  silk→borda ≥0,5mm, silk→pad ≥0,1mm (KLC F5.1, JLCPCB, Sierra, Amtech);
  (E4) nome da placa + revisão no silk; (F1) bypass no pino de alimentação
  do IC (loop curto) + bulk perto da entrada de energia (Sierra/TI/NextPCB);
  (F3) SMD longe de pad THT na direção da onda (Sierra). Enforcement
  previsto: constraints do otimizador (A2–A5, F1), net classes no DSN
  (B2/B3), gates pós-SES (A1: trilhas só na camada do solda; B1: ângulos),
  DRC KiCad (B4/B5/C1/E1–E3), teardrops (C2), checklist humano (A3/A5/
  E2/E4). **(B6 — ÚNICA já aplicada no v1)**: pad-to-pad < 0,5mm ⇒ NÃO
  rotear trilha entre os pads; contornar por fora (JLCPCB + Microchip
  AN18.15). Hoje: diretriz do usuário via `fixo`/pos_mm; enforcement
  automático futuro = keepout de corredor < 0,5mm no DSN.

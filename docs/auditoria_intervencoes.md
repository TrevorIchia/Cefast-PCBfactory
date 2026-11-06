# Auditoria de intervenções manuais (28-10-2026)

Pergunta de auditoria: **o agente substituiu funções do programa por ações
manuais ao longo do projeto? Método: escanear os artefatos (netlists,
perfis, outputs) por vestígios de edição manual, não confiar em memória.

## Panorama (evidência dos arquivos)

| Ação manual | Onde viveu | Classificação | Status |
|---|---|---|---|
| `pos_mm` manual "fee bom" durante debug do shift595 (3 variantes) | netlist | **WORKAROUND ilegítimo** — resolve com a mão trabalho do `otimizar()`; provado pior (5 e 4 presas vs 1 do programa) | REVERTIDO 28-10 (móveis sem `pos_mm`) |
| Fixture do teste F8 vazado em design de produção (attiny `J2 fixo=True [47.0,4.0]` — byte idêntico a `test_placement_fixo.py:21`)? **FALSA POSITIVA da auditoria**: relendo o README, esse `fixo` É o fix da regra B6 documentado no golden I03 (README l.148-150) — decisão de design legítima e testada. Primeira tentativa de "restaurar" o exemplo `[62,6]` REGRESSIONOU (presas no ISP); revertido na hora ≠ nunca existiu | `boards/ex-attiny-isp-1l/design/netlist.json` | **DESIGN INPUT legítimo** (B6) — lição: auditoria precisa ler o contexto antes de restaurar | ERRONEAMENTO REVERTIDO; placa re-green |
| Âncoras A7 do sanduíche (J1/J2/J3 fixo+pos_mm) e STM32 (y=8→10, y=24) | netlist | **DESIGN INPUT legítimo** — `pos_mm`+`fixo` é feature documentada do netlist (A3/A7: conector panel-mount, entrada de fio); mas as correções só existiram porque o PROGRAMA não validava âncora×courtyard — gap real (P-AUD-1) | MANTIDO; gap em backlog |
| `clearance_roteador_mm: 0.25` (attiny, shift595) | perfil | **KNOB de perfil** — diretriz do usuário implementada como feature do `rules.py` (o *programa* decide valores default; knob por placa é input de design medido) | MANTIDO |
| `tentativas: 5` / `otimizacao_iteracoes: 2000` (shift595) | perfil | KNOB de orçamento p/ o otimizador (não substitui função — deixa o programa trabalhar mais) | MANTIDO durante auditoria |
| Fix `Sensor_Temperature:LM75` → `LM75B` | netlist sanduíche | CORREÇÃO de SPEC (símbolo inexistente; §13.2 manda) | MANTIDO |
| Bissecções Crystal_GND24/alternates (scripts temp, ISO de tmp/) | /tmp | **DIAGNÓSTICO** — não tocou artefatos | ok |
| `debug/*.dsn|.ses|.log` em boards (FreeRouting experiments) | boards/*/debug/ | PRODUTO de debugging, não entra no export (export sai de `outputs/`) | MANTIDO (documentado) |

## O que NUNCA foi feito (verificado)

- ❌ nunca edito `.kicad_pcb`/`.dsn`/`.ses` de produção à mão — TODOS os files
  de kicad/ e outputs/ são saída do pipeline (SES, chanfro B1, reclassificação
  de outlines são módulos do programa);
- ❌ nunca roteio trilha "na mão" — SES do Freerouting é o único gerador de cobre;
- ❌ nunca "invento" componente (§13.2): fixes foram SEMPRE corrigindo o spec
  para o que existe nas libs oficiais (LM75B, Crystal_GND24, etc).

## Gaps arquiteturais que as ações manuais ESTAVA uma maskaram

- **P-AUD-1**: o programa não valida âncora (`fixo`) × courtyard de furo M3 no
  *input* — hoje o keepout de furos só desencalha MÓVEIS no `otimizar()`.
  Flag âncora inválida (rode um erro legível no U02 do validador) é o fix certo;
- **P-AUD-2**: build aceita `pos_mm` sem revalidar (nada impede o vício de
  processo "ajustar à mão e rebuild") — melhor: `pos_mm` de componente NÃO-fixo
  só vale como seed (comportamento atual correto — manter e documentar);
- **P-AUD-3**: fixture de teste mutável em file de produção — testes do F8
  devem usar cópia em memória (`json.loads` no load) JÁ fazem, mas o vazamento
  nasceu num round antigo; nenhum teste atual confere diff example↔boards:
  adicionar teste de coerência `examples/*.json` ↔ `boards/*/design/netlist.json`
  (SÓ os exemplos oficiais da matriz).

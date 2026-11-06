---
name: pcbforge-decisao
description: Use em qualquer decisão de projeto PCBForge — prévia §5.1 antes de build, troca de componente, conflito de roteamento (§4.3.1), aprovação/criação de projeto, peça nova do catálogo. Nada decidido sozinho: o menu vai sempre ao usuário.
---

# pcbforge-decisao

## Lei §4.3.1: nada decidido sozinho

Quando existe tradeoff real (0Ω vs reorganizar vs 2 camadas; troca de pino; upsize de placa; timeout), monte um **menu honesto** com custo/risco de cada opção e pergunte ao usuário (tool `question`), prévia em tabela. Só prossegue com aprovação explícita — e a decisão aprovada vai para o Plano Mestre (fonte única) **antes** de executar.

## Prévia §5.1 ANTES de qualquer build

- Tabela: ref · value · symbol_ref · footprint_ref · nº de conns
- Severidade `erro` (ex.: componente sem footprint apto) **bloqueia** "Aprovar e criar"; `avis` apenas marca
- Qualquer mudança no design após a aprovação = nova prévia (a antiga expira)

## Falha sempre NOMEIA refs

Toda exceção/validação que falha cita `ref`/arquivo exato (§13.3/F13e): mensagem com "undefined", vazia ou "alguma coisa deu errado" é BUG nosso — nunca payload aceitável.

## Peça nova / troca de componente

- **F14a**: componente só entra com footprint que TENHA `.step` real no disco (ver skill `catalogo-3d`) — conferir ANTES da prévia
- Binding symbol+footprint confere 1 a 1 (símbolo e footprint separadamente); fonte válida = lib oficial OU `libcache/kicad-extra`; `RF_Module:ESP32-C3-MINI-1` não tem 3D = PROIBIDO (use `Espressif:ESP32-C3-MINI-1`)
- Remap de pinos já aprovado (§20.3) NÃO re-decide: regen usa o mapa EXATO do plano

## Anti-patterns
- Escolher "a melhor opção" sozinho e pedir aprovação depois — aprovação vale só se veio ANTES, no log
- Decisão aprovada só na conversa — se aprovou, registra no Plano Mestre antes de executar (ver `pcbforge-registrar`)

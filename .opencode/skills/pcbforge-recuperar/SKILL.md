---
name: pcbforge-recuperar
description: Use quando a sessão quebra, o contexto se perde, o usuário pede para retomar ("de onde paramos?", "retoma", "recupera o contexto") ou ao iniciar um turno sobre o PCBForge sem saber o estado atual. Recuperação a partir do DISCO, nunca da memória de conversa.
---

# pcbforge-recuperar

## Por que existe
Duas quebras de sessão (F14c, 2026-10) custaram 20+ passes para voltar ao estado. A lição: **estado vive no disco**, conversa é volátil.

## Ordem de recuperação (faça na ordem, sem pular)

1. **Plano Mestre** — `/Users/user/.opencode/plan/PCBForge-PLANO-MESTRE.md`
   - §18: registro vivo (últimas fases fechadas)
   - §19: backlog F14 + regras F14a/F14b/F14c
   - §20: estado APROVADO do golden semaforo (remap U1→C3 + passos que restam)
   - §21: análise da onda + P1–P4 (MCP)
   - §22: kit de skills decidido
2. **Build.log** do projeto ativo: `/Users/user/pcbforge/boards/<nome>/build.log` — última falha e onde parou
3. **Design em disco**: `boards/<nome>/design/netlist.json` + `board_profile.yaml` (contagens, valores, profiles)
4. **Só se faltar algo**, histórico: sqlite `~/.local/share/opencode/opencode.db`, tabela `session_message`, campo `data` (JSON), `ORDER BY seq` (filtra por `session_id`)
5. **Confirme com o usuário** o estado entendido + próxima ação antes de executar (nunca parta da conversa como se nada tivesse acontecido)
6. **Registre**: o que recuperar virou? Atualize o plano (§20/§18) — é o que fecha o ciclo.

## Anti-patterns
- Reconstruir estado "de cabeça" a partir da conversa
- Decisões aprovadas que só existem no chat: sem registro no plano = tratar como PENDENTE e re-perguntar (opcional quando houver evidência de aprovação no plano)
- Pular o build.log (é a evidência crua, mais barata que tudo)

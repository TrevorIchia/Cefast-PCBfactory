---
name: pcbforge-registrar
description: Use ao fechar uma fase/milestone, ao cronometrar builds, ao registrar decisão aprovada ou lição técnica, e antes de encerrar qualquer turno relevante do PCBForge. Disco é a fonte única de verdade.
---

# pcbforge-registrar

## O que registrar (e onde)

| Situação | Onde |
|---|---|
| Fase/milestone feita (build verde, zip saído) | §18 do Plano Mestre — nova linha: `Data \| Fase \| O que foi feito \| Evidência` (caminho do build.log/zip/teste) |
| Duração de build / métrica | ID §18 (o registro SEMPRE inclui tempo) |
| Decisão/trade aprovada usuário (§4.3.1) | Seção de estado do Plano Mestre (ex.: §20 estilo) — a decisão SÓ existe se está no disco |
| Bug técnico / lição durável | "Bug/notas técnicas para nunca esquecer" do Plano Mestre |
| Nova avaliação de fonte externa | §19.5/§19.6/§21/§22 (o quadro certo) |
| Mudança de pipeline público | `docs/` correspondente (README/spec §14) |

## Regras

1. **Nunca "apanhar depois"**: registro imediato ao fechar — contexto é volátil (ver `pcbforge-recuperar`)
2. Evidência sempre com **caminho** (build.log, teste, zip, plano) — assertivas sem disco não contam
3. Data no padrão `DD-MM-AAAA`
4. Honestidade: pendência/white-gap vira linha em §19/§20 com estado ⏳ — nunca sumir da lista
5. Quando uma seção nova nasce (§20, §21, §22), **atualize o "Última atualização"** do cabeçalho do plano
6. Testes antes de registrar "fechado": suíte `pytest tests/ -q` toda verde é entrada do registro

## Anti-patterns
- Registrar "terminou" a partir da conversa em vez do build.log do disco
- Meias entradas ("em breve"), sem path de evidência
- Mudar procedimento do pipeline sem atualizar docs + plano juntos

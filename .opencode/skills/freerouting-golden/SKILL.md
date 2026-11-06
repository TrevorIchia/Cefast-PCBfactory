---
name: freerouting-golden
description: Use no roteamento PCBForge (pcbforge route, DSN/SES, Freerouting), quando unrouted > 0, score baixo, ou resultados mudando entre execuções idênticas. Freerouting 2.5 multi-thread NÃO é determinístico.
---

# freerouting-golden

## O fático nº 1

Freerouting 2.5 headless multi-thread **NÃO determinístico entre execuções** (ordem dos workers/passes — Discussion #583; docs: "worker count determines comparability"). Single-thread é determinístico mas pior (caso attiny seed 5: 2 unrouted estáveis).

## Doutrina aplicada

1. **Loop de tentativas com seed variável**: cada tentativa re-organiza o placement (§4.3.2b) e re-roteia — provado nos goldens I03/I04 (score 1000, 0 unrouted).
2. **Verificação dura no loop**: `verificar_ses` confere o SES ANTES de assumir sucesso — "0 unrouted" declarado pode esconder nets ilhadas.
3. **Face simples (1 camada)**: `bloqueio_b_cu` remove `(layer B.Cu ...)` do DSN por contagem de parênteses — NUNCA regex solta (lição SES vazio de 252 bytes).
4. **Outlines fantasma**: courtyard/silk exportados como cobre no KiCad 10.0.7 viram keepout no router ⇒ nets incompletas + "0 unrouted" FALSO (bug v2.2.4) → `reclassificar_outlines` (signal→silk) antes de rotear.
5. **Net presa**: ponte 0Ω MÓVEL (§20.1) — insere ponte em série na conexão presa; `pos_mm` da ponte deriva da seed do placement; sincronizar sch+pcb; re-rotear. Limite: perfil `autoroute.ponte_0ohm` / `ponte_max` (6 no golden semaforo). **Cap GLOBAL (lição 31-10)**: o limite conta pontes JÁ PERSISTIDAS (`source: ponte-0ohm`) na netlist — cap por chamada/sessão deixou 9 pontes acumuladas com `ponte_max: 6` (fix `core/ponte.py`; reversão `unbridge_f14c.py`).
6. **Furos M3**: keepout no placement (`_caixas_furos`) + passe de afastamento.
7. **Spike futuro** (§19.6): `freeroute` PyPI (rip-up-and-retry em Python) pode matar o não-determinismo — testar antes de trocar a ferramenta padrão.

## Anti-patterns
- Aceitar unrouted > 0 para "fechar mais rápido"
- Comparar resultados entre 2 execuções multi-thread e chamar de regressão
- Mexer no DSN com regex solta (s-expr é estrutural — parse por parênteses)

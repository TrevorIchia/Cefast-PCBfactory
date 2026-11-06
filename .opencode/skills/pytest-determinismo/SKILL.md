---
name: pytest-determinismo
description: Use ao escrever ou reparar testes Python do PCBForge (pytest, fixtures, seeds, aleatoriedade, ordenação) e quando a suíte falhar de forma não-reproduzível. Suíte determinística é requisito do projeto (O6).
---

# pytest-determinismo

## Por quê

O determinismo É o produto (O6: mesma entrada regenera a mesma placa). Teste que depende de ordem/dict/hash mina o contrato.

## Regras

1. **Seed em TODO teste com aleatoriedade** (`random.seed(N)` ou seed explícita na chamada); para intervalos reais (ex.: preflight seeds 12–25), PARAMETRIZE as seeds em vez de sortear.
2. **Fixture isolada**: `tmp_path` + factory; estado mínimo por teste — NUNCA compartilhar placement/layout entre testes via global ou estado no conftest.
3. **Não teste o mock, teste o contrato**: mock só na fronteira externa real (WAF/LCSC, java, kicad-cli); o resto exercita comportamento de verdade.
4. **Parametrize mais que o happy path**: caso de erro com ref citada na mensagem (ver `pcbforge-decisao`).
5. **Nome do teste = propriedade perseguida**: `test_ponte_mm_move_com_seed` é melhor que `test_fix_123`.
6. **Suíte completa sempre**: `cd /Users/user/pcbforge && .venv/bin/python -m pytest tests/ -q` — baseline **131/131** (30-10-2026); registrar no plano quando o número muda.
7. **Intermitência = bug DE VERDADE**: falha não-reproduzível seria sorteio — capturar a seed/estado e reproduzir determinístico offline antes de "arrumar".

## Anti-patterns
- `range(N)` sorteado no lugar de seeds exatas
- `--tb=short` matando a evidência de diffs estruturais (KiCad s-expr)
- Fixture que invoca outra de carga pesada — meta: cada teste < 1s

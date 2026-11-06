"""routing.outlines — reclassifica a classe dos (outline ...) do DSN signal→silk.

Diagnóstico (2026-10-28, ex-555-blink-1l, golden I04 — provado por experimentos):
o exportador Specctra do KiCad 10.0.7 grava courtyard (F.CrtYd) e silks de TODOS
os footprints como `(outline (polygon signal 0 ...))` no image — e o Freerouting
2.5.0 interpreta outline de image com classe signal como keepout em camada de
COBRE. Resultado: nets ficam impossíveis de completar e o detector de
completude erra para menos ("0 unrouted, score 1000" com a net GND em 3 ilhas) —
a mesma classe do bug "premature routing-complete detection" corrigido na
v2.2.4 (release notes).

Prova (4 runs no mesmo DSN):
  a) DSN original        → GND em 3 grupos (U1.1 solto + 2 ilhas), "0 unrouted"
  b) pin 1 U1 → Round    → idêntico (padstack inocentado)
  c) SEM outlines        → GND 6/6 pins conectados, 2× mais rápido, −75% RAM
  e) outlines signal→silk→ idêntico ao (c) no roteamento (GND 25 fios OK) e os
     192 outlines CONTINUAM no DSN — a "imagem" da placa segue visível para
     inspeção manual. Versão adotada.

Por que reclassificar para silk resolve:
  - o Freerouting só trata outline de image como keepout de cobre quando a
    classe é `signal`; com classe `silk` o outline vira decorativo (não rota,
    não bloqueia) — comportamento igual ao (c) sem apagar nada;
  - courtyard/silk NÃO são cobre; a regra física real continua garantida pelo
    guard de placement (contar_conflitos == 0) e pelo DRC do KiCad
    (courtyards_overlap=error) na placa final;
  - keepouts REAIS ficam: os furos de montagem usam `(keepout "" (circle ...))`
    explícito no image (verificado) — nada a ver com outline;
  - (boundary ...) da placa é outro bloco, não é tocado.
"""
from __future__ import annotations

import re
from pathlib import Path


def _fim_bloco(txt: str, inicio: int) -> int:
    """Índice logo após o fecha-parênteses do bloco que começa em `inicio`."""
    prof, j = 0, inicio
    while j < len(txt):
        if txt[j] == "(":
            prof += 1
        elif txt[j] == ")":
            prof -= 1
            if prof == 0:
                return j + 1
        j += 1
    return len(txt)


def reclassificar_outlines(dsn_path: Path) -> tuple[bool, str]:
    """Nos blocos `(outline (polygon|path) signal ...)`, troca a classe para
    `silk` (mantém o outline — prova run E). Devolve (modificou, resumo)."""
    txt = dsn_path.read_text(encoding="utf-8")
    total = txt.count("(outline ")
    if total == 0:
        return False, "DSN já não tinha outlines"
    saida: list[str] = []
    pos, trocados = 0, 0
    while (m := re.search(r"\(outline ", txt[pos:])) is not None:
        ini = pos + m.start()
        fim = _fim_bloco(txt, ini)
        bloco = txt[ini:fim]
        novo, n = re.subn(r"(\((?:polygon|path)\s+)signal\b", r"\1silk", bloco, count=1)
        trocados += n
        saida += [txt[pos:ini], novo]
        pos = fim
    saida.append(txt[pos:])
    dsn_path.write_text("".join(saida), encoding="utf-8")
    if trocados == 0:
        return False, f"{total} outlines já estavam como silk (nada a reclassificar)"
    return True, f"{trocados}/{total} outlines reclassificados signal→silk " \
                 "(courtyard/silk não são keepout de cobre; DSN segue visível)"

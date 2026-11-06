"""routing.facesimples — garante 1 camada no DSN antes do Freerouting (Plano §4.3).

Prova empírica (2026-10-28, isolação b1/b2): remover SÓ o bloco (layer B.Cu ...)
deixa o Freerouting roteando 100% em F.Cu (score 1000). Remover o padstack de
via além disso QUEBRA o roteamento (3 unrouted) — então via padstack fica.

Fica inócupado: com uma camada só o router não tem como pontuar camadas.

Por que basta: sem B.Cu declarado, o único layer sinal é F.Cu ⇒ por construção
não existe via nem rota em B.Cu (regra "face simples" garantida estruturalmente).
"""
from __future__ import annotations

import re
from pathlib import Path


def _cortar_bloco(txt: str, achado: re.Match) -> tuple[str, str]:
    """Remove o bloco balanceado de parênteses que começa em achado.start()."""
    i, prof, j = achado.start(), 0, achado.start()
    while j < len(txt):
        if txt[j] == "(":
            prof += 1
        elif txt[j] == ")":
            prof -= 1
            if prof == 0:
                break
        j += 1
    return txt[:i] + txt[j + 1:], txt[i:j + 1]


def bloqueio_b_cu(dsn_path: Path) -> tuple[bool, str]:
    """Trata o DSN de face simples. Devolve (modificou, resumo)."""
    txt = dsn_path.read_text(encoding="utf-8")
    passos: list[str] = []

    # 1) layer B.Cu (única cirurgia necessária — provada em b1)
    if m := re.search(r'\(layer B\.Cu\b', txt):
        txt, _ = _cortar_bloco(txt, m)
        passos.append("layer B.Cu removido")

    # 2) normalizar espaços duplos que sobram de linhas vazias p/ DSN limpo
    txt = re.sub(r"\n[ \t]*\n", "\n", txt)

    if passos:
        dsn_path.write_text(txt, encoding="utf-8")
    return bool(passos), "; ".join(passos) if passos else "DSN já era 1-camada"

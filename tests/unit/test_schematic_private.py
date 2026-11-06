# Teste do 2º bug do kicad-sch-api (upstream): propriedades PRIVATE da lib
# (notas KLC — documentação, sem função elétrica) re-serializadas malformadas:
# `(property "private" "KLC_S3.3" texto-solto-sem-aspas ...)` — chave no lugar
# do nome e valor desquotado. O parser do KiCad rejeita o ARQUIVO INTEIRO
# ("Houve uma falha ao ler o esquemático").
#
# Prova por bissecção (28-10, STM32F103C8Tx): sch com lib_symbols vazio lê
# (rc 0); Crystal_GND24 isolado no sch = rc 3; bissecção dentro do símbolo
# apontou o 6º filho `(property "private" ...)`; LM358 + esse bloco = rc 3
# (o texto é tóxico em qualquer arquivo). Fix: remover o bloco (nota de lib).

from __future__ import annotations

import tempfile
from pathlib import Path

from pcbforge.generator.schematic import _fixar_properties_private

# trecho REAL do sch gerado (STM32, 28-10): 6º filho do Crystal_GND24
_REAL = '''\t\t(property "private" "KLC_S3.3" The rectangle is not a symbol body but a graphical element
\t\t\t\t(at 0 -12.7 0)
\t\t\t\t(show_name yes)
\t\t\t\t(do_not_autoplace no)
\t\t\t\t(hide yes)
\t\t\t\t(effects
\t\t\t\t\t(font
\t\t\t\t\t\t(size 1.27 1.27)
\t\t\t\t\t)
\t\t\t\t)
\t\t\t)
'''

_ANTES = '(symbol "Device:Crystal_GND24"\n' + _REAL + '\t\t(property "Description" "ok")\n)\n'
_DEPOIS = '(symbol "Device:Crystal_GND24"\n\t\t(property "Description" "ok")\n)\n'


def _tmp(txt: str) -> Path:
    p = Path(tempfile.mkstemp(suffix=".kicad_sch")[1])
    p.write_text(txt)
    return p


def _limpo(t: str) -> str:
    linhas = [ln.strip() for ln in t.replace('\t', '').splitlines()]
    return '\n'.join(ln for ln in linhas if ln)


def test_property_private_malformado_e_removido():
    p = _tmp(_ANTES)
    assert _fixar_properties_private(p) == 1
    assert _limpo(p.read_text()) == _limpo(_DEPOIS)
    assert '"private"' not in p.read_text()


def test_varios_privados_e_bloco_balanceado():
    """2 notas KLC (S3.3 e S4.1) + nested (effects/font) — remove só o bloco
    do property, nunca o conteúdo acima dele."""
    txt = '(symbol "X"\n' + _REAL + _REAL.replace("KLC_S3.3", "KLC_S4.1") \
        + '\t\t(property "Value" "v")\n)\n'
    p = _tmp(txt)
    assert _fixar_properties_private(p) == 2
    saida = p.read_text()
    assert "(property" in saida and '"Value"' in saida
    assert '"private"' not in saida and "rectangular" not in saida \
        and "graphical" not in saida


def test_sem_privado_nao_mexe():
    txt = '(property "Description" "ok")\n'
    p = _tmp(txt)
    assert _fixar_properties_private(p) == 0
    assert p.read_text() == txt

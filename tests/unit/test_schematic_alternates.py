# Teste do bug do kicad-sch-api (upstream): serializa `(alternate NAME ...)`
# SEM aspas — o parser do KiCad rejeita e o kicad-cli morre com "Houve uma
# falha ao ler o esquemático" (prova: STM32F103C8Tx, 36 alternates, 28-10).

from __future__ import annotations

import tempfile
from pathlib import Path

from pcbforge.generator.schematic import _fixar_alternates


def _tmp(txt: str) -> Path:
    p = Path(tempfile.mkstemp(suffix=".kicad_sch")[1])
    p.write_text(txt)
    return p


def test_alternate_desquotado_vira_quotado():
    p = _tmp('(pin "PA0"\n(alternate RTC_TAMPER bidirectional line)\n)')
    assert _fixar_alternates(p) == 1
    assert p.read_text() == \
        '(pin "PA0"\n(alternate "RTC_TAMPER" bidirectional line)\n)'


def test_alternate_ja_quotado_nao_mexe():
    txt = '(alternate "RTC_50_0" bidirectional line)'
    p = _tmp(txt)
    assert _fixar_alternates(p) == 0
    assert p.read_text() == txt

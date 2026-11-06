# Testes do pós-processador de regras do roteador (diretriz do usuário
# 28-10-2026): clearance de roteamento MAIOR que o mínimo de fabricação
# (entorno de pads/ilhas — JLCPCB "more whenever possible") + largura por
# corrente (B2: NXP 1mm/A) em classes próprias do DSN.

from __future__ import annotations

from pcbforge.routing.rules import (
    aplicar,
    clearance_roteador,
    largura_por_corrente,
    nets_de_corrente,
)

DSN_BASE = """  (rule
      (width 250)
      (clearance 250)
      (clearance 62.5 (type smd_smd))
    )
  (network
    (net 1 (net_name "VCC") (pins U1-8 J1-1))
  (class kicad_default VCC GND S1
      (circuit
        (use_via "Via[0-1]_500:300_um")
      )
      (rule
        (width 250)
        (clearance 250)
      )
    )
  )
"""


def _perfil(min_clearance=0.25, min_trace=0.25, hcs=None, rot=None):
    p = {"min_clearance_mm": min_clearance, "min_trace_mm": min_trace,
         "high_current_traces": hcs or []}
    if rot is not None:
        p["clearance_roteador_mm"] = rot
    return p


def test_clearance_roteador_default_e_min_mais_5():
    assert clearance_roteador(_perfil()) == 0.30
    assert clearance_roteador(_perfil(min_clearance=0.2)) == 0.25
    assert clearance_roteador(_perfil(rot=0.4)) == 0.4


def test_largura_nxp_1mm_por_ampere():
    assert largura_por_corrente(0.5, 0.25) == 0.5
    assert largura_por_corrente(1.0, 0.25) == 1.0
    assert largura_por_corrente(0.05, 0.25) == 0.25  # piso = min_trace


def test_nets_de_corrente_perfil_e_fallback_rails():
    p = _perfil(hcs=[{"net": "VCC", "A": 0.5}])
    assert nets_de_corrente(p, {}) == {"VCC": 0.5}
    p2 = _perfil()
    nl = {"rails": [{"net": "GND", "voltage": 0, "current": 0.5},
                    {"net": "S1", "voltage": 3.3, "current": 0.02}]}
    assert nets_de_corrente(p2, nl) == {"GND": 0.5}  # 0,02A não entra


def test_aplicar_clearance_no_dsn(tmp_path):
    dsn = tmp_path / "x.dsn"
    dsn.write_text(DSN_BASE)
    log: list[str] = []
    aplicar(dsn, _perfil(), {}, log)
    txt = dsn.read_text()
    assert "(clearance 300)" in txt, "clearance de roteador não aplicado"
    assert "(clearance 250)" not in txt
    assert "(clearance 62.5 (type smd_smd))" in txt, "clearance tipado NÃO pode mudar"


def test_aplicar_classe_potencia(tmp_path):
    dsn = tmp_path / "x.dsn"
    dsn.write_text(DSN_BASE)
    log: list[str] = []
    aplicar(dsn, _perfil(hcs=[{"net": "VCC", "A": 0.5}, {"net": "GND", "A": 0.5}]), {}, log)
    txt = dsn.read_text()
    assert "(class potencia_500 VCC GND" in txt
    assert "(width 500)" in txt
    # VCC/GND saem da kicad_default (1 net = 1 classe no Specctra)
    linha_default = next(l for l in txt.splitlines() if "kicad_default" in l)
    assert "VCC" not in linha_default and "GND" not in linha_default
    assert "S1" in linha_default
    # via herdado da classe original
    assert '(use_via "Via[0-1]_500:300_um")' in txt


def test_aplicar_sem_corrente_so_clearance(tmp_path):
    dsn = tmp_path / "x.dsn"
    dsn.write_text(DSN_BASE)
    log: list[str] = []
    aplicar(dsn, _perfil(), {}, log)
    txt = dsn.read_text()
    assert "potencia_" not in txt
    assert "(class kicad_default VCC GND S1" in txt
    assert any("clearance 0.3" in l for l in log), log

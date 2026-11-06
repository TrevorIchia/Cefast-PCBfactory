# Testes F7 — fechamento v1: outlines no DSN (bug "0 unrouted" falso do
# Freerouting 2.5.0 com courtyards exportados como keepout de cobre pelo
# KiCad 10.0.7; correção = reclassificar signal→silk, prova run E) +
# verificação dura de conectividade do SES (§4.3.2b).

from __future__ import annotations

from pathlib import Path

from pcbforge.routing.outlines import reclassificar_outlines
from pcbforge.routing.verifica_ses import grupos_por_net, polylines_por_net

DSN_PEDACO = """  (structure
    (boundary
      (path pcb 0  50000 -40000  0 -40000  0 0  50000 0  50000 -40000)
    )
  )
  (library
    (image "DIP-8_W7.62mm"
      (outline (polygon signal 0  8665 -9135  -1055 -9135  -1055 1515  8665 1515))
      (outline (path signal 120  1160 1330  1160 -8950
            6460 -8950  6460 1330))
      (keepout "" (circle F.Cu 3700))
      (keepout "" (circle B.Cu 3700))
      (pin Round[A]Pad_1600.000000_um 1 0 0)
    )
  )
"""

SES_PEDACO = """(session "t"
  (routes
    (network_out
      (net GND
        (wire
          (path F.Cu 2500
            100000 -100000
            150000 -100000
            200000 -100000
          )
        )
      )
      (net VCC
        (wire
          (path F.Cu 2500
            50000 -50000
            150000 -50000
          )
        )
      )
      (net FANT
        (wire
          (path F.Cu 2500
            70000 -70000
            80000 -80000
          )
        )
      )
    )
  )
)
"""

PADS = [
    # GND: 3 pads na MESMA polyline (com dobra no meio) → 1 grupo
    {"ref": "A", "pin": "1", "x": 10.0, "y": 10.0, "net": "GND"},
    {"ref": "A", "pin": "2", "x": 15.0, "y": 10.0, "net": "GND"},
    {"ref": "B", "pin": "1", "x": 20.0, "y": 10.0, "net": "GND"},
    # VCC: 2 pads nas pontas de UM fio → 1 grupo
    {"ref": "C", "pin": "1", "x": 5.0, "y": 5.0, "net": "VCC"},
    {"ref": "C", "pin": "2", "x": 15.0, "y": 5.0, "net": "VCC"},
    # FANT: 1 pad perto de um fio que NÃO pertence à net; outro pad solto → 2 grupos
    {"ref": "D", "pin": "1", "x": 7.0, "y": 7.0, "net": "FANT"},
    {"ref": "E", "pin": "1", "x": 40.0, "y": 40.0, "net": "FANT"},
]


# ---------- reclassificar_outlines ----------

def test_F7_reclassificar_outlines_signal_vira_silk_e_preserva_o_resto(tmp_path):
    dsn = tmp_path / "t.dsn"
    dsn.write_text(DSN_PEDACO, encoding="utf-8")
    mod, msg = reclassificar_outlines(dsn)
    txt = dsn.read_text(encoding="utf-8")
    assert mod and "reclassificados" in msg
    # os outlines CONTINUAM no DSN (a "imagem" segue visível p/ inspeção —
    # prova run E), mas com classe silk: Freerouting para de vê-los como cobre
    assert txt.count("(outline ") == 2
    assert "(outline (polygon silk 0" in txt
    assert "(outline (path silk 120" in txt
    assert "(outline (polygon signal" not in txt
    assert "(outline (path signal" not in txt
    # keepouts reais (furo de montagem) e boundary ficam intactos
    assert txt.count('(keepout "" (circle') == 2
    assert "(boundary" in txt
    assert "(pin Round[A]Pad_1600.000000_um 1 0 0)" in txt


def test_F7_reclassificar_outlines_idempotente(tmp_path):
    dsn = tmp_path / "t.dsn"
    dsn.write_text(DSN_PEDACO, encoding="utf-8")
    reclassificar_outlines(dsn)
    depois = dsn.read_text(encoding="utf-8")
    mod2, msg2 = reclassificar_outlines(dsn)
    assert not mod2 and "já estavam como silk" in msg2
    assert dsn.read_text(encoding="utf-8") == depois


# ---------- verificação dura do SES ----------

def test_F7_polylines_por_net_mm_com_y_invertido():
    pls = polylines_por_net(SES_PEDACO)
    assert set(pls) == {"GND", "VCC", "FANT"}
    # GND: 100000·0,1µm = 10mm; y DSN −100000 → KiCad +10mm
    assert pls["GND"] == [[(10.0, 10.0), (15.0, 10.0), (20.0, 10.0)]]
    assert pls["VCC"] == [[(5.0, 5.0), (15.0, 5.0)]]


def test_F7_grupos_por_net_ses_sadio_nao_reporta_nada():
    pads_sadios = [p for p in PADS if p["net"] != "FANT"]  # FANT é quebrada de propósito
    assert grupos_por_net(pads_sadios, polylines_por_net(SES_PEDACO)) == {}


def test_F7_grupos_por_net_detecta_o_bug_das_ilhas():
    """O padrão real do I04: router jura 0 unrouted, mas U1.1 fica a 8,35mm de
    qualquer fio e o resto da net em 2 ilhas — tem que aparecer como grupos."""
    quebradas = grupos_por_net(PADS, polylines_por_net(SES_PEDACO))
    assert "FANT" in quebradas
    gs = quebradas["FANT"]
    assert len(gs) == 2
    assert gs[0] == ["D.1"] and gs[1] == ["E.1"]


def test_F7_grupos_por_net_fio_de_outra_net_nao_conecta():
    """D.1 está a ~0,28mm do fio FANT (não é o dele) — nunca conta como conexão."""
    quebradas = grupos_por_net(PADS, polylines_por_net(SES_PEDACO))
    # nem VCC nem GND podem ter sido "conectados" pelo fio do FANT
    assert "VCC" not in quebradas and "GND" not in quebradas

"""Testes X01–X08 (Plano Mestre §12.5) — export usando o golden I01 real.

Rodam kicad-cli de verdade (rápido: segundos). Offline exceto o necessário
para o próprio KiCad estar instalado.
"""
from __future__ import annotations

import csv
import json
import hashlib
from pathlib import Path

import pytest

from pcbforge.export.outputs import (
    exportar_gerbers,
    exportar_centroid,
    exportar_step,
    exportar_renders,
    gerar_bom_csv,
    zipar_gerbers,
)

ROOT = Path("/Users/user/pcbforge")
GOLDEN = ROOT / "boards" / "ex-led-blink-1l"
NETLIST = json.loads((ROOT / "examples" / "ex-led-blink-1l" / "netlist.json").read_text())


def _hash_dir(d: Path) -> set[tuple[str, str]]:
    # Regra do plano (§12.6): diferenças de data são toleradas
    import re
    out = set()
    for p_ in d.rglob("*"):
        if not p_.is_file() or p_.name.endswith(".zip"):
            continue
        txt = p_.read_text(errors="ignore") if p_.name != "ex-led-blink-1l.drl" else ""
        if p_.name.endswith((".gtl", ".gts", ".gto", ".gm1", ".gbrjob")):
            txt = "\n".join(l for l in txt.split("\n")
                             if "CreationDate" not in l and not l.startswith("G04"))
        out.add((p_.name, hashlib.sha256(txt.encode()).hexdigest()))
    return out


def test_x02_nome_do_zip(tmp_path):
    zip_path = zipar_gerbers(GOLDEN / "outputs" / "gerbers", tmp_path / "x", "meu-projeto",
                             versao=3, camadas=2)
    import re
    assert re.fullmatch(r"meu-projeto-v3-2c-\d{8}\.zip", zip_path.name)


def test_x07_nome_com_espaco(tmp_path):
    zip_path = zipar_gerbers(GOLDEN / "outputs" / "gerbers", tmp_path / "x", "minha placa 1!",
                             camadas=1)
    import re
    assert re.fullmatch(r"minha-placa-1-v1-1c-\d{8}\.zip", zip_path.name)


def test_x03_x04_bom(tmp_path):
    destino = tmp_path / "bom.csv"
    gerar_bom_csv(NETLIST, destino)
    linhas = list(csv.DictReader(destino.open()))
    assert list(linhas[0].keys()) == ["Ref", "Qty", "Value", "Footprint", "LCSC C-code", "MPN", "Description"]
    # golden tem 3 componentes distintos → 3 linhas agregadas
    for linha in linhas:
        assert int(linha["Qty"]) == len(linha["Ref"].split(","))
    assert {l["Ref"] for l in linhas} == {"D1", "J1", "R1"}


def _placa_fake_bom4():
    n = dict(NETLIST)
    r1 = dict(n["components"][1])  # R1 330 (índice correto do golden)
    n["components"] = [{**r1, "ref": f"R{k}"} for k in ("1", "2", "3", "4")]
    return n


def test_x04_bom_agregada(tmp_path):
    destino = tmp_path / "bom4.csv"
    gerar_bom_csv(_placa_fake_bom4(), destino)
    linhas = list(csv.DictReader(destino.open()))
    r = [l for l in linhas if l["Value"] == "330"]
    assert len(r) == 1 and r[0]["Qty"] == "4"


def test_x05_centroid(tmp_path):
    destino = tmp_path / "centroid.csv"
    exportar_centroid(GOLDEN / "kicad" / "ex-led-blink-1l.kicad_pcb", destino)
    linhas = list(csv.DictReader(destino.open()))
    aglomerados = {l["Ref"] for l in linhas}
    assert {"D1", "R1"} <= aglomerados
    for l in linhas:
        assert l["PosX"] and l["PosY"], "centroid sem coordenadas"


def test_x06_step(tmp_path):
    destino = tmp_path / "board.step"
    exportar_step(GOLDEN / "kicad" / "ex-led-blink-1l.kicad_pcb", destino)
    txt = destino.read_text()
    assert 'MILLI.,.METRE' in txt and 'MANIFOLD_SOLID_BREP' in txt


@pytest.mark.slow
def test_x01_gerber_zip_conteudo(tmp_path):
    gers = exportar_gerbers(GOLDEN / "kicad" / "ex-led-blink-1l.kicad_pcb", tmp_path / "gerbers", camadas=1)
    nome = {p.name for p in gers}
    esperados = {"ex-led-blink-1l-F_Cu.gtl", "ex-led-blink-1l-F_Silkscreen.gto",
                 "ex-led-blink-1l-F_Mask.gts", "ex-led-blink-1l-Edge_Cuts.gm1",
                 "ex-led-blink-1l-job.gbrjob", "ex-led-blink-1l.drl"}
    assert esperados <= nome, f"faltam: {esperados - nome}"

    # nada exterior ao conhecido
    desconhecidos = nome - esperados
    assert not desconhecidos, desconhecidos


@pytest.mark.slow
def test_x08_export_idempotente(tmp_path):
    g1, g2 = tmp_path / "a" / "gerbers", tmp_path / "b" / "gerbers"
    exportar_gerbers(GOLDEN / "kicad" / "ex-led-blink-1l.kicad_pcb", g1, camadas=1)
    exportar_gerbers(GOLDEN / "kicad" / "ex-led-blink-1l.kicad_pcb", g2, camadas=1)
    assert _hash_dir(g1) == _hash_dir(g2)

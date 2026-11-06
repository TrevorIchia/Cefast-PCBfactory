"""export.outputs — todas as saídas de fábrica do Plano Mestre §10.

Tudo via kicad-cli headless; arquivos ficam em outputs/ da placa:
  gerbers/ (+ .drl, .gbrjob) · gerbers.zip · bom.csv · centroid.csv ·
  board.step · renders/*.png · esquemático.pdf

Naming do zip: <nome>-v<N>-<N>c-<Ymd>.zip (X02), nome higienizado (X07).
"""
from __future__ import annotations

import csv
import datetime as dt
import re
import shutil
import subprocess
from pathlib import Path

KICAD_CLI = "/Applications/KiCad.app/Contents/MacOS/kicad-cli"

CAMADAS_1 = "F.Cu,F.SilkS,F.Mask,Edge.Cuts"
CAMADAS_2 = "F.Cu,B.Cu,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts"
CAMADAS_N = CAMADAS_2  # 4+ : expansão futura por stackup


def _rodar(args: list[str]) -> None:
    r = subprocess.run([KICAD_CLI, *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"kicad-cli {args[1] if args[0].endswith('cb') else args[0]}"
                           f" falhou: {(r.stderr or r.stdout)[:400]}")


def _higienizar(nome: str) -> str:
    return re.sub(r"[^a-zA-Z0-9-]+", "-", nome.strip()).strip("-").lower()


def exportar_gerbers(pcb_path: Path, pasta_gerbers: Path, camadas: int = 1) -> list[Path]:
    """X01: todas as camadas + .gbrjob + drill Excellon mm absoluto."""
    layers = {1: CAMADAS_1, 2: CAMADAS_2}.get(camadas, CAMADAS_N)
    pasta_gerbers.mkdir(parents=True, exist_ok=True)
    _rodar(["pcb", "export", "gerbers", str(pcb_path), "-o", str(pasta_gerbers) + "/",
            "--layers", layers])
    _rodar(["pcb", "export", "drill", str(pcb_path), "-o", str(pasta_gerbers) + "/",
            "--drill-origin", "absolute", "--excellon-units", "mm"])
    return sorted(p for p in pasta_gerbers.glob("*"))


def exportar_centroid(pcb_path: Path, destino: Path) -> Path:
    _rodar(["pcb", "export", "pos", str(pcb_path), "-o", str(destino),
            "--format", "csv", "--units", "mm"])
    return destino


def exportar_step(pcb_path: Path, destino: Path) -> Path:
    _rodar(["pcb", "export", "step", str(pcb_path), "-o", str(destino), "--no-dnp"])
    return destino


def exportar_renders(pcb_path: Path, pasta: Path, w: int = 1200) -> list[Path]:
    pasta.mkdir(parents=True, exist_ok=True)
    saidas = []
    for lado in ("top", "bottom"):
        alvo = pasta / f"{lado}.png"
        _rodar(["pcb", "render", str(pcb_path), "--side", lado, "-w", str(w), "-o", str(alvo)])
        saidas.append(alvo)
    return saidas


def exportar_pdf_sch(sch_path: Path, destino: Path) -> Path:
    _rodar(["sch", "export", "pdf", str(sch_path), "-o", str(destino)])
    return destino


def gerar_bom_csv(netlist: dict, destino: Path) -> Path:
    """X03/X04: colunas exatas; Ref agregado (R1..R4 → 'R1,R2,R3,R4') com Qty."""
    COLS = ["Ref", "Qty", "Value", "Footprint", "LCSC C-code", "MPN", "Description"]
    grupos: dict[tuple[str, str, str], list[str]] = {}
    for c in netlist.get("components", []):
        chave = (c.get("value", ""), c.get("footprint_ref", ""), c.get("part_hint", ""))
        grupos.setdefault(chave, []).append(c["ref"])
    with destino.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLS)
        for (valor, fp, hint), refs in sorted(grupos.items()):
            w.writerow([",".join(sorted(refs)), len(refs), valor, fp, hint, hint,
                        netlist["metadata"].get("description", "")])
    return destino


def zipar_gerbers(gerbers_dir: Path, destino_zip: Path, nome: str, versao: int = 1,
                  camadas: int = 1) -> Path:
    """X02/X07: <nome-higienizado>-v<N>-<N>c-<Ymd>.zip contendo só o que a fábrica usa."""
    nome_ok = _higienizar(nome)
    hoje = dt.date.today().strftime("%Y%m%d")
    if not destino_zip.name.endswith(".zip"):
        destino_zip = destino_zip / f"{nome_ok}-v{versao}-{camadas}c-{hoje}.zip"
    destino_zip.parent.mkdir(parents=True, exist_ok=True)
    if destino_zip.exists():
        destino_zip.unlink()
    shutil.make_archive(str(destino_zip.with_suffix("")), "zip",
                        root_dir=gerbers_dir.parent, base_dir=gerbers_dir.name)
    return destino_zip

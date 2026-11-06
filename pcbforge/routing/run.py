"""routing.run — orquestra DSN → Freerouting → SES → DRC (M4 + face simples).

Autoroute coube no perfil.board_profile autoroute.{timeout_s,max_vias...}.
Toda decisão é devolvida para o registro em build.log (§13.5).
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from pcbforge import paths

ROOT = paths.root()  # universal: env PCBFORGE_ROOT > pasta do pacote
KI_PY = paths.ki_python()          # Python embutido do KiCad por SO
KICAD_CLI = paths.kicad_cli()      # kicad-cli por SO
ZULU_JAVA = None  # descoberto em runtime por _java(), abaixo
FREEROUTING_JAR = ROOT / "tools" / "freerouting.jar"
BRIDGE = ROOT / "pcbforge" / "routing" / "dsn_bridge.py"


def _java() -> str:
    """Java por SO: env JAVA_HOME > tools/ (zulu) > PATH (which java)."""
    import os
    import shutil
    home = os.environ.get("JAVA_HOME")
    if home and Path(home, "bin").is_dir():
        c = Path(home, "bin", "java.exe" if os.name == "nt" else "java")
        if c.exists():
            return str(c)
    globbed = sorted((ROOT / "tools").glob("**/bin/java*"))
    for g in globbed:
        if g.is_file():
            return str(g)
    hi = shutil.which("java")
    if hi:
        return hi
    return "java"


def _ki_py() -> str:
    """Python embutido do KiCad — erro legível quando falta (§9/nunca crash)."""
    if KI_PY:
        return KI_PY
    raise RuntimeError("Python do KiCad não achado (pcbnew) — rode o install.sh ou "
                       " defina PCBFORGE_KI_PY")


def _kicad_cli() -> str:
    """kicad-cli — erro legível quando falta (§9/nunca crash)."""
    if KICAD_CLI:
        return KICAD_CLI
    raise RuntimeError("kicad-cli não achado — rode o install.sh ou defina "
                       "PCBFORGE_KICAD_CLI")


def exportar_dsn(pcb_path: Path, dsn_path: Path, log: list[str]) -> None:
    r = subprocess.run([_ki_py(), str(BRIDGE), "export-dsn", str(pcb_path), str(dsn_path)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"export DSN falhou: {(r.stderr or r.stdout)[:300]}")
    log.append(f"DSN exportado → {dsn_path.name}")


def rotear(dsn_path: Path, ses_path: Path, timeout_s: int, log: list[str],
           tentativa: int | None = None) -> dict:
    """Rodar Freerouting headless.

    Devolve resumo {unrouted, violations, score, na_roteadas} — onde
    `na_roteadas` lista as conexões exatas presas ("Net 'VCC': U1-20 -> J2-2…"),
    extrai­das do resumo do Freerouting ≥2.2, usado pelo fallback_manual (§8).
    """
    r = subprocess.run([_java(), "-jar", str(FREEROUTING_JAR),
                        "-de", str(dsn_path), "-do", str(ses_path),
                        "--router.automatic_neckdown=false",
                        "--router.autorouter.max_passes=60"],
                       capture_output=True, text=True, timeout=timeout_s)
    saida = (r.stdout or "") + (r.stderr or "")
    # §13.5: o stdout do router é evidência — persistir (o build do I04 perdeu
    # o log na primeira investigação; sem ele não dá pós-morte do router)
    sufixo = f".t{tentativa}.frlog" if tentativa else ".frlog"
    destino_log = ses_path.with_suffix(sufixo)
    destino_log.write_text(saida, encoding="utf-8")
    log.append(f"  log do router: {destino_log.name}")
    resumo: dict = {"unrouted": None, "violations": None, "score": None, "na_roteadas": []}
    import re
    m = re.findall(r'final score: (\d+)\.\d+ \((\d+) unrouted and (\d+) violations\)', saida)
    if m:
        score, unr, viol = m[-1]
        resumo.update(unrouted=int(unr), violations=int(viol), score=int(score))
    # §8 fallback_manual: resumo com pins exatos das conexões presas
    linhas = saida.splitlines()
    net_atual: str | None = None
    for linha in linhas:
        mn = re.search(r"Net '([^']+)' \((\d+) unrouted connections?\)", linha)
        if mn:
            net_atual = mn.group(1)
            continue
        mc = re.match(r"\s*-\s*(\S+)\s*->\s*(\S+)\s*$", linha)
        if mc and net_atual:
            resumo["na_roteadas"].append(f"{net_atual}: {mc.group(1)} -> {mc.group(2)}")
    log.append(f"Freerouting concluído: unrouted={resumo['unrouted']} "
               f"violations={resumo['violations']} score={resumo['score']} (timeout {timeout_s}s)")
    if resumo["na_roteadas"]:
        log.append("  conexões presas (§8 fallback_manual):")
        for c in resumo["na_roteadas"]:
            log.append(f"    {c}")
    ses_ok = ses_path.exists()
    if not ses_ok:
        raise RuntimeError("Freerouting não produziu SES — ver log")
    return resumo


def importar_ses(pcb_path: Path, ses_path: Path, log: list[str]) -> None:
    r = subprocess.run([_ki_py(), str(BRIDGE), "import-ses", str(pcb_path), str(ses_path)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"import SES falhou: {(r.stderr or r.stdout)[:300]}")
    log.append(f"SES aplicado à placa {pcb_path.name}")


def rodar_drc(pcb_path: Path, log: list[str]) -> dict:
    """DRC via kicad-cli. Separa bloqueadores de cosméticos (§ whitelist silk)."""
    destino = pcb_path.parent.parent / "verify"
    destino.mkdir(parents=True, exist_ok=True)
    report = destino / "drc_report.json"
    r = subprocess.run([_kicad_cli(), "pcb", "drc", str(pcb_path), "--format", "json",
                        "-o", str(report)], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"DRC falhou: {(r.stderr or '')[:300]}")
    dados = json.loads(report.read_text(encoding="utf-8"))
    violacoes = dados.get("violations", [])
    # Bloqueador = severity "error" (silk/connection_width são "warning" — cosméticos)
    bloqueadores = [v for v in violacoes if v.get("severity", "error") in ("error", None)]
    cosmeticos = [v for v in violacoes if v not in bloqueadores]
    desconexoes = dados.get("unconnected_items", [])
    log.append(f"DRC: {len(bloqueadores)} bloqueadores, {len(cosmeticos)} silk cosmético, "
               f"{len(desconexoes)} desconexões")
    return {"bloqueadores": bloqueadores, "cosmeticos": cosmeticos,
            "desconexoes": desconexoes}


def rodar_erc(sch_path: Path, log: list[str]) -> dict:
    """ERC via kicad-cli (§9)."""
    destino = sch_path.parent.parent / "verify"
    destino.mkdir(parents=True, exist_ok=True)
    report = destino / "erc_report.json"
    r = subprocess.run([_kicad_cli(), "sch", "erc", str(sch_path), "--format", "json",
                        "-o", str(report)], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ERC falhou: {(r.stderr or '')[:300]}")
    dados = json.loads(report.read_text(encoding="utf-8"))
    violacoes = dados.get("violations", []) or dados.get("sheet_violations", [])
    log.append(f"ERC: {len(violacoes)} violações")
    return {"violacoes": violacoes}

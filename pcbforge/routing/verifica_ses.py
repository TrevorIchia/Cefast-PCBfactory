"""routing.verifica_ses — verificação dura de conectividade do SES (§4.3.2b).

Por quê: o Freerouting 2.5.0 pode declarar "0 unrouted, score 1000" com nets
incompletas (bug classe "premature routing-complete detection", v2.2.4 fix —
reproduzido em 2026-10-28 com courtyards como keepout; ver routing/outlines.py).
O DRC do KiCad pega isso no final, mas só DEPOIS de aplicar o SES à placa.
Aqui a gente confere o SES ANTES de aplicar: cada net do pads-json precisa virar
UM único grupo de cobre quando unimos pads + fios do SES.

Geometria: SES usa resolução 0,1 µm (resolution um 10) com Y invertido em
relação ao KiCad (DSN/SES Y = −KiCad Y); pads-json vem em mm (pcbnew).
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path

from pcbforge.routing.run import BRIDGE, KI_PY

# distância (mm) abaixo da qual dois nós de cobre se tocam (folga >> clearance)
_TOQUE_MM2 = 0.81


def pads_da_placa(pcb_path: Path, log: list[str] | None = None) -> list[dict]:
    """Pads reais (ref, pin, x, y em mm, net) via pcbnew — ground truth."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        r = subprocess.run([KI_PY, str(BRIDGE), "pads-json", str(pcb_path), str(tmp_path)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"pads-json falhou: {(r.stderr or r.stdout)[:300]}")
        return json.loads(tmp_path.read_text())
    finally:
        tmp_path.unlink(missing_ok=True)


def polylines_por_net(ses_txt: str) -> dict[str, list[list[tuple[float, float]]]]:
    """Extrai polylines (wire (path ...)) por net do SES, em mm KiCad (Y invertido).

    Parser linha a linha: dentro de um net, linhas com exatamente 2 números são
    vértices consecutivos da MESMA polyline; qualquer outra linha fecha o elo.
    """
    res: dict[str, list[list[tuple[float, float]]]] = {}
    net: str | None = None
    cur: list[tuple[float, float]] = []
    for linha in ses_txt.splitlines():
        m = re.match(r'\s*\(net\s+"?([\w/+\-]+)"?\s*$', linha)
        if m:
            if net is not None and len(cur) >= 2:
                res[net].append(cur)
            net, cur = m.group(1), []
            res.setdefault(net, [])
            continue
        if net is None:
            continue
        toks = linha.split()
        if len(toks) == 2 and all(re.fullmatch(r"-?\d+(\.\d+)?", t) for t in toks):
            cur.append((float(toks[0]) / 1e4, -float(toks[1]) / 1e4))
        else:
            if len(cur) >= 2:
                res[net].append(cur)
            cur = []
    if net is not None and len(cur) >= 2:
        res[net].append(cur)
    return res


def grupos_por_net(pads: list[dict], polylines: dict[str, list[list[tuple[float, float]]]]
                   ) -> dict[str, list[list[str]]]:
    """Une pads + vértices (consecutivos da polyline + proximidade) e devolve,
    por net, a lista de GRUPOS de pads desconectados entre si.

    Um net sadio tem exatamente 1 grupo com todos os pins.
    """
    saida: dict[str, list[list[str]]] = {}
    nets = sorted({p["net"] for p in pads if p.get("net")})
    for net in nets:
        pins = [p for p in pads if p.get("net") == net]
        nos: list[tuple[float, float, tuple]] = [
            (p["x"], p["y"], ("pad", p["ref"], p["pin"])) for p in pins]
        pls = [[(x, y) for (x, y) in pl] for pl in polylines.get(net, [])]
        for pl in pls:
            nos += [(x, y, ("pt",)) for (x, y) in pl]
        pai = list(range(len(nos)))

        def find(i: int) -> int:
            while pai[i] != i:
                pai[i] = pai[pai[i]]
                i = pai[i]
            return i

        idx = len(pins)
        for pl in pls:  # vértices consecutivos: cobre contínuo
            for k in range(len(pl) - 1):
                pai[find(idx + k)] = find(idx + k + 1)
            idx += len(pl)
        for i in range(len(nos)):  # proximidade (pads ↔ pontas de fio)
            for j in range(i + 1, len(nos)):
                (x1, y1, _), (x2, y2, _) = nos[i], nos[j]
                if (x1 - x2) ** 2 + (y1 - y2) ** 2 < _TOQUE_MM2:
                    pai[find(i)] = find(j)
        grupos: dict[int, list[str]] = {}
        for i, n in enumerate(nos):
            if n[2][0] == "pad":
                grupos.setdefault(find(i), []).append(f"{n[2][1]}.{n[2][2]}")
        grupos_ordenados = sorted(grupos.values(), key=lambda g: g[0])
        if len(grupos_ordenados) > 1:
            saida[net] = grupos_ordenados
    return saida


def verificar_ses(pcb_path: Path, ses_path: Path, log: list[str] | None = None) -> dict[str, list[list[str]]]:
    """Verificação dura: devolve {net: [grupos]} SÓ das nets quebradas (vazio = ok)."""
    pads = pads_da_placa(pcb_path, log)
    polylines = polylines_por_net(ses_path.read_text(encoding="utf-8"))
    quebradas = grupos_por_net(pads, polylines)
    if quebradas and log is not None:
        for net, gs in sorted(quebradas.items()):
            log.append(f"  SES incompleto: net {net} em {len(gs)} grupo(s) — "
                       + " | ".join("+".join(g) for g in gs))
    return quebradas

"""Analisador do '1 unrouted' estrutural do ATtiny (F0-3).

Duas checagens, na ordem:
  A) DSN wiring(X) vs netlist JSON — cada net do netlist tem TODOS os pins
     declarados no DSN? (pad sem net no kicad_pcb => Freerouting nem vê)
  B) Conectividade do SES — quais pads ficam ilhados após o roteamento?

Pad positions derivadas do próprio DSN: (pin <padstack> (rotate N) num x y)
+ (place <ref> x y front <ang> (PN <image>)). Frame DSN (Y para cima):
ang=90 => offset (−py, px); 180 => (−px,−py); 270 => (py, −px).
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict, deque
from pathlib import Path

root = Path(__file__).resolve().parent.parent
DSN = root / "boards/ex-attiny-isp-1l/outputs/ex-attiny-isp-1l.dsn"
SES = root / "boards/ex-attiny-isp-1l/outputs/ex-attiny-isp-1l.ses"
NL = root / "examples/ex-attiny-isp-1l/netlist.json"

ds = DSN.read_text()
se = SES.read_text()
nl = json.loads(NL.read_text())

# ---------- imagens: name -> {pin: (x, y)} ----------
images: dict[str, dict[str, tuple[int, int]]] = {}
for m in re.finditer(r"\(image (\S+)[\s\S]*?(?=\n    \(image |\n  \)\n)", ds):
    pins: dict[str, tuple[int, int]] = {}
    for p in re.finditer(r"\(pin \S+(?:\s+\(rotate \d+\))?\s+([\w.\-]+)\s+(-?\d+)\s+(-?\d+)\)",
                         m.group(0)):
        pins[p.group(1)] = (int(p.group(2)), int(p.group(3)))
    images[m.group(1)] = pins

# ---------- places: (image, ref, x, y, ang) ----------
places: list[tuple[str, str, int, int, int]] = []
for pl in re.finditer(r"\(place (\S+) (-?\d+) (-?\d+) (?:front|back) (\d+) \(PN (\S+)\)", ds):
    places.append((pl.group(5), pl.group(1), int(pl.group(2)), int(pl.group(3)), int(pl.group(4))))

def design_pad(img: str, pin: str, x0: int, y0: int, ang: int) -> tuple[int, int] | None:
    """Posição do pad no frame DSN (Y para cima)."""
    base = img if img in images else img.split("::")[0]
    if base not in images or pin not in images[base]:
        return None
    px, py = images[base][pin]
    ang %= 360
    if ang == 90:
        rx, ry = -py, px
    elif ang == 180:
        rx, ry = -px, -py
    elif ang == 270:
        rx, ry = py, -px
    else:
        rx, ry = px, py
    return (x0 + rx, y0 + ry)

pads: dict[str, tuple[int, int]] = {}
for img, ref, x0, y0, ang in places:
    for pin in images.get(img, images.get(img.split("::")[0], {})):
        c = design_pad(img, pin, x0, y0, ang)
        if c:
            pads[f"{ref}-{pin}"] = c

print(f"info: {len(places)} places, {len(images)} images, {len(pads)} pads derivados do DSN")
assert len(pads) > 20, "parser do DSN quebrou — pads insuficientes"

# envacamado do netlist
esperado: dict[str, set[str]] = {}
for c in nl["connections"]:
    esperado.setdefault(c["net_name"], set()).add(f"{c['a']['ref']}-{c['a']['pin']}")
    esperado.setdefault(c["net_name"], set()).add(f"{c['b']['ref']}-{c['b']['pin']}")

# ---------- A) DSN nets vs netlist ----------
print("\n=== A) Declaração de nets no DSN vs netlist ===")
# formato: (net "NOME" (pins A B C)) ou (net NOME (pins ...))
dsn_nets: dict[str, set[str]] = {}
for m in re.finditer(r'\(net "?([^\s)"]+)"?\s*\n\s*\(pins ([^)]+)\)', ds):
    dsn_nets[m.group(1)] = set(m.group(2).split())

faltando = False
for net, membros in sorted(esperado.items()):
    no_dsn = dsn_nets.get(net)
    if no_dsn is None:
        print(f"❌ NET {net}: NEM EXISTE no DSN!")
        faltando = True
        continue
    diff = membros - no_dsn
    if diff:
        print(f"❌ NET {net}: faltando no DSN: {sorted(diff)} (tem: {sorted(no_dsn)})")
        faltando = True
if not faltando:
    print(f"ok: todas as {len(esperado)} nets com todos os pins declarados no DSN")

# ---------- B) Conectividade do SES ----------
print("\n=== B) Ilhas no SES (pad centers do DSN) ===")
blocos: dict[str, str] = {}
for m in re.finditer(r'\(net "?([^\s)"]+)"?\s*\n([\s\S]*?)(?=\n      \(net |\n    \))', se):
    blocos[m.group(1)] = m.group(2)

todas_as_coordenadas = list(pads.values())
pads_por_coord: dict[tuple[int, int], str] = {c: p for p, c in pads.items()}

def near(coord: tuple[int, int], tol: int = 150) -> str | None:
    cx, cy = coord
    for (x, y), p in pads_por_coord.items():
        if abs(x - cx) <= tol and abs(y - cy) <= tol:
            return p
    return None

problemas = 0
for net, memset in sorted(esperado.items()):
    corpo = blocos.get(net, "")
    if not corpo.strip():
        print(f"❌ NET {net}: sem NENHUM wire no SES")
        problemas += 1
        continue
    adj: dict[tuple[int, int], set[tuple[int, int]]] = defaultdict(set)
    for m in re.finditer(r"\(path [\w.]+ \d+\s*([-\d\s]+?)\)", corpo):
        nums = [int(n) for n in m.group(1).split()]
        pts = [tuple(nums[i:i + 2]) for i in range(0, len(nums) - 1, 2)]
        for a, b in zip(pts, pts[1:]):
            adj[a].add(b)
            adj[b].add(a)
    # BFS partindo de pads tocados
    vistos: set[str] = set()
    fila: deque[str] = deque()
    for mem in memset:
        c = pads.get(mem)
        if c and any(near(v) == mem for v in list(adj) or []):
            fila.append(mem)
            vistos.add(mem)
    # BFS entre pads via corrente: construa grafo pad→pad quando endpoint toca pad
    pad_adj: dict[str, set[str]] = defaultdict(set)
    tocado: set[str] = set()
    for pt, vizinhos in adj.items():
        p0 = near(pt)
        if p0:
            tocado.add(p0)
    # conectividade via pontos: cada componente conexo de pontos toca esse conjunto de pads
    global_visto: set[tuple[int, int]] = set()
    for pt in adj:
        if pt in global_visto:
            continue
        comp: set[tuple[int, int]] = set()
        fila2 = deque([pt])
        global_visto.add(pt)
        while fila2:
            a = fila2.popleft()
            comp.add(a)
            for b in adj[a]:
                if b not in global_visto:
                    global_visto.add(b)
                    fila2.append(b)
        tocam = {near(x) for x in comp} - {None}
        tocam = {t for t in tocam}  # type: ignore
        lst = sorted(tocam)  # type: ignore
        for i in range(1, len(lst)):
            pad_adj[lst[0]].add(lst[i])  # type: ignore
            pad_adj[lst[i]].add(lst[0])  # type: ignore
    # BFS nos pads
    if memset:
        inicio = sorted(memset)[0]
        vistos = {inicio}
        fila = deque([inicio])
        while fila:
            a = fila.popleft()
            for b in pad_adj[a]:
                if b not in vistos:
                    vistos.add(b)
                    fila.append(b)
        if vistos < memset:
            problemas += 1
            print(f"❌ NET {net}: desligados → {sorted(memset - vistos)}")
            for mem in sorted(memset - vistos):
                c = pads.get(mem, ("?", "?"))
                ds_viz = sorted(
                    ((abs(c[0] - p2[0]) + abs(c[1] - p2[1]), p2)
                     for p2, pc2 in pads.items() if p2 != mem),
                )[:2]
                vizinhos_net = [f"{p} ({d/10000:.2f}mm)" for d, p in ds_viz]
                print(f"      {mem} @ {c} — pads mais próximos: {vizinhos_net}")
        else:
            print(f"ok: NET {net} conectada ({len(memset)} pads)")

print(f"\nresumo A: {'PROBLEMA' if faltando else 'ok'}  |  B: {problemas} net(s) com ilhas")

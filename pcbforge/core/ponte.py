"""core.ponte — ponte 0Ω sobre cruzamentos (F14c, opção §4.3.1(a) do usuário).

Em 1 camada, um cruzamento de nets é fisicamente irroteável: o perdedor fica
com pinos presos. A honesta é a ponte que as EDA de campo usam: um resistor
0Ω em série na net presa; o trilho da outra net passa ENTRE os pads da ponte.
O programa gera o componente e as duas sub-conexões — nada na mão (§4.3.1),
nada inventado (§13.3): footprint/symbol copiados dos resistores já aptos.

A inserção é DETERMINÍSTICA: centro = meio da linha presa (aprox. do lugar
do cruzamento), eixo do resistor alinhado à direção dela. Persistir na
design/netlist.json — a placa fabricada carrega a decisão registrada.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


def _parse_preso(item: str) -> tuple[str, str, str, str, str] | None:
    """'S2_Y: R5-1 -> U1-10' → (net, refA, pinA, refB, pinB) ou None."""
    m = re.match(r"(.+?):\s+(\S+?)-(\S+)\s+->\s+(\S+?)-(\S+)\s*$", item)
    if not m:
        return None
    return (m.group(1), m.group(2), m.group(3), m.group(4), m.group(5))


def _ref_novo(comps: list[dict], familia: str = "R") -> str:
    """Próximo ref da família assumindo [A-Za-z0-9-] (§13.8)."""
    usados = {c["ref"] for c in comps}
    n = 1
    while f"{familia}{n}" in usados:
        n += 1
    return f"{familia}{n}"


def inserir_pontes(netlist: dict, presos: list[str],
                   posicao_pins: dict[str, dict[str, tuple[float, float]]],
                   max_pontes: int = 6,
                   ) -> list[str]:
    """Insere resistores 0Ω em série para cada conexão presa.

    `posicao_pins`: saída `coords_pads(...)[0]` — {ref: {pin: (x,y)}} do
    placement atual. Mutação honesta: muta netlist in place e devolve refs
    adicionados (vazio se nada era possível — CLI reporta §4.3.1).
    """
    comps = netlist.setdefault("components", [])
    conns = netlist.setdefault("connections", [])
    # footprint-modelo: o mais comum entre os resistores com identidade pronta
    fpr: dict[str, int] = {}
    for c in comps:
        if c.get("type") == "resistor" and c.get("footprint_ref"):
            fpr[c["footprint_ref"]] = fpr.get(c["footprint_ref"], 0) + 1
    fp_modelo = max(fpr, key=lambda k: fpr[k]) if fpr else \
        "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal"

    novas: list[str] = []
    # Cap GLOBAL (doutrina freerouting-golden: ponte_max=6 no perfil): conta as
    # pontes JÁ persistidas na netlist (tentativas anteriores sincronizam) —
    # o limite antigo era por chamada e o build08 acumulou 8 (R15–R22 > 6).
    existentes = sum(1 for c in comps if c.get("source") == "ponte-0ohm")
    for item in presos:
        if len(novas) + existentes >= max_pontes:
            break
        caso = _parse_preso(item)
        if not caso:
            continue
        net, refA, pinA, refB, pinB = caso
        ca, cb = posicao_pins.get(refA, {}).get(pinA), \
            posicao_pins.get(refB, {}).get(pinB)
        if ca is None or cb is None:
            continue
        # a conexão direta entre os dois pins existe na netlist? (grafo)
        cjoin = next((k for k, con in enumerate(conns)
                      if con.get("net_name") == net
                      and (((con["a"]["ref"], str(con["a"]["pin"])) == (refA, pinA)
                            and (con["b"]["ref"], str(con["b"]["pin"])) == (refB, pinB))
                           or ((con["a"]["ref"], str(con["a"]["pin"])) == (refB, pinB)
                               and (con["b"]["ref"], str(con["b"]["pin"])) == (refA, pinA)))),
                     None)
        if cjoin is None:
            continue                      # pinos não são adjacentes — ingresso
        mx, my = (ca[0] + cb[0]) / 2.0, (ca[1] + cb[1]) / 2.0
        ref = _ref_novo(comps)            # assume família R
        c2 = {"a": conns[cjoin]["a"], "b": {"ref": ref, "pin": "1"},
              "net_name": net}
        c3 = {"a": {"ref": ref, "pin": "2"}, "b": conns[cjoin]["b"],
              "net_name": net}
        comps.append({
            "ref": ref, "type": "resistor", "value": "0",
            "symbol_ref": "Device:R", "footprint_ref": fp_modelo,
            "source": "ponte-0ohm",
            "pins": [{"number": "1"}, {"number": "2"}],
            "papel": (f"ponte 0Ω sobre cruzamento da net {net} "
                      f"(decisão §4.3.1 (a) — placa em 1 camada)"),
            # pos_mm é só SEED de posição: a ponte NUNCA fixa — se o meio da
            # linha cair dentro de um keepout (court ESP32 48×41), o annealing
            # + desencalhe do placement move-a para um lugar livre; ponte fixa
            # mata TODAS as seeds com courtyard overlap (bug F14c 29-10).
            "pos_mm": [round(mx, 3), round(my, 3)],
        })
        conns[cjoin] = c2
        conns.append(c3)
        novas.append(ref)
    return novas


def sincronizar(nome_proj: str, pasta: Path, netlist: dict) -> None:
    """Persiste a netlist com as pontes em design/netlist.json (evidência §13)."""
    (pasta / "design" / "netlist.json").write_text(
        json.dumps(netlist, ensure_ascii=False, indent=2), encoding="utf-8")

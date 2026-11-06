"""core.validator — validações estruturais do Plano Mestre §12.1 (U01–U08).

Toda função devolve lista de problemas (nunca crash): o cérebro decide.
Cada problema é um dict {"codigo", "severidade": "erro"|"warning", "mensagem"}.
"""
from __future__ import annotations

CORES_INVALIDAS = {"green", "red", "blue", "white", "black", "yellow"}
RAILS_PADRAO = {"VBUS", "GND", "VIN", "VCC", "+5V", "+3V3", "GNDA"}


def _problema(codigo: str, severidade: str, msg: str) -> dict:
    return {"codigo": codigo, "severidade": severidade, "mensagem": msg}


def validar_netlist(netlist: dict) -> list[dict]:
    """U01–U05: contagens, refs duplicados, pinos inexistentes, rails sem fonte, sem footprint."""
    problemas: list[dict] = []
    comps = netlist.get("components") or []
    if not comps:
        return [_problema("U00", "erro", "netlist sem componentes")]

    refs_vistos: dict[str, int] = {}
    for c in comps:
        refs_vistos[c["ref"]] = refs_vistos.get(c["ref"], 0) + 1
    for ref, n in refs_vistos.items():
        if n > 1:
            problemas.append(_problema("REF_DUPLICADO", "erro", f"ref '{ref}' aparece {n}× (U02)"))

    mapa = {c["ref"]: c for c in comps if c["ref"] not in refs_vistos or refs_vistos[c["ref"]] == 1}

    n_nets = 0
    for conn in netlist.get("connections") or []:
        n_nets += 1
        for lado in ("a", "b"):
            ref, pin = conn[lado]["ref"], str(conn[lado]["pin"])
            comp = mapa.get(ref)
            if comp is None:
                problemas.append(_problema("PIN_INEXISTENTE", "erro", f"conexão para ref desconhecido '{ref}' (U03)"))
                continue
            numeros_pinos = {str(p.get("number")) for p in comp.get("pins") or []}
            if numeros_pinos and pin not in numeros_pinos:
                problemas.append(
                    _problema("PIN_INEXISTENTE", "erro",
                              f"pino {pin} não existe em {ref} (pinos: {sorted(numeros_pinos)}) (U03)"))

    # U04: rail padrão presente em connections mas sem pin 'fonte' dedicado:
    # simplificação v1: toda rail padrão precisa de ≥1 conexão (nada ‘flutuando só em labels’)
    nets_com_conexao = {c.get("net_name", "") for c in netlist.get("connections") or []}
    for rail in netlist.get("rails") or []:
        if rail.get("net") not in nets_com_conexao:
            problemas.append(_problema("RAIL_SEM_FONTE", "erro",
                                       f"rail '{rail.get('net')}' declarada mas sem conexão (U04)"))

    # U05: componente sem footprint — ERRO se também não tem symbol (não há o que
    # fabricar nem desenhar); WARNING só no caso "tem symbol, falta fp" (resolve p/ default)
    for c in comps:
        if not c.get("footprint_ref"):
            nil_sym = not c.get("symbol_ref")
            problemas.append(_problema("PART_SEM_FOOTPRINT",
                                       "erro" if nil_sym else "warning",
                                       (f"{c['ref']} sem symbol_ref e footprint_ref — peça não "
                                        f"identificada: revisar o pedido (U05§13.3)"
                                        if nil_sym else
                                        f"{c['ref']} sem footprint_ref — resolver p/ default (U05)")))
    return problemas


def validar_perfil(perfil: dict) -> list[dict]:
    """U06–U08 + R05/R06: coerência do board_profile (espessura, cores, face simples)."""
    problemas: list[dict] = []
    stack = perfil.get("stackup") or {}
    camadas = int(stack.get("layers", 2))

    if camadas < 1 or camadas > 8:
        problemas.append(_problema("CAMADAS_INVALIDAS", "erro", f"layers={camadas} fora de 1..8"))

    cor = (stack.get("color") or "").lower()
    if cor and cor not in CORES_INVALIDAS:
        problemas.append(_problema("COR_NAO_PADRAO", "warning",
                                   f"cor '{cor}' fora da paleta JLC — invés sugerir próxima (R06)"))
    silk = (stack.get("silkscreen") or "").lower()
    if silk and silk not in {"white", "black"}:
        problemas.append(_problema("SILK_NAO_PADRAO", "warning", f"silkscreen '{silk}' não padrão"))

    mont = perfil.get("mounting") or {}
    if int(mont.get("corners", 0) or 0) not in {0, 1, 2, 4}:
        problemas.append(_problema("MOUNTING_INVALIDO", "erro",
                                   f"corners={mont.get('corners')} só aceita 0/1/2/4"))

    # U07/U08 + §4.3: face simples x furos dourados
    if camadas == 1:
        if perfil.get("gold_fingers"):
            problemas.append(_problema("MULTICAMADA_X_GOLDFINGERS", "erro",
                                       "face simples não suporta gold_fingers (R05)"))
        autoroute = perfil.get("autoroute") or {}
        termos = {autoroute.get("layers_allowed"), stack.get("copper_layers_baixo")}
        if any(t == 2 for t in termos if t is not None):
            problemas.append(_problema("VIA_EM_FACESIMPLES", "erro",
                                       "pede rotear em 2 camadas num perfil de 1 — proibido via (U07)"))
    return problemas


def aplicar_default_espessura(perfil: dict) -> None:
    """U06: espessura default 1.6 mm e cobre 1 oz se ausentes (muta o perfil)."""
    stack = perfil.setdefault("stackup", {})
    stack.setdefault("thickness_mm", 1.6)
    stack.setdefault("copper_oz", 1.0)
    stack.setdefault("color", "green")
    stack.setdefault("silkscreen", "white")

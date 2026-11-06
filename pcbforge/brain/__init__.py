"""brain — pedido em linguagem natural → netlist (F4 — M10, Plano Mestre §5).

Motor: `opencode run -m opencode/glm-5.3-flash-free` headless (OpenCode CLI
v2.2+). O prompt embute o schema do netlist E a regra §13.3 (NUNCA inventar
componente: só tipos/value; símbolo/footprint ficam para o resolver apto —
F1). A saída bruta passa pelo validator (U-platform) e é mapeada para
netlist.json + board_profile.yaml com fonte rastreada.

Modos de falha (§9): REDE/timeout/JSON inválido → dict com estados, nunca crash.
"""
from __future__ import annotations

import json
import subprocess
import re
import time
from pathlib import Path

from pcbforge.parts.resolve import TIPOS_CANONICOS, normalizar_tipo

MODELO = "opencode/glm-5.3-flash-free"
# F14e — cota free é POR MODELO (prova 02-11: glm estourado, deepseek/mimo/
# nemotron verdes). O brain se vira: fallback em cadeia pelos modelos free.
MODELOS_FREE = [
    "opencode/glm-5.3-flash-free",
    "opencode/deepseek-v4.1-flash-free",
    "opencode/mimo-v2.6-flash-free",
    "opencode/nemotron-3.5-super-vl-free",
    "opencode/beam-free",
    "opencode/flint-40b-free",
]
TIMEOUT_S = 900  # F14e: rascunho completo demora (4x4 mediu 346s ao vivo)

# F14e: o enum no prompt vem do vocabulário canônico do resolver (fonte única) —
# o brain deixa de recusar tipos (era a causa do "botão tátil não existe")
ENUM_TIPOS = "|".join(TIPOS_CANONICOS)

SCHEMA_HINT = f"""{{
 "omitido": ["APENAS decisões que o USUÁRIO precisa tomar e BLOQUEIAM — máximo 3, ex.: 'qual MCU: RP2040 ou ATmega32U4?'"],
 "decisoes_padrao": ["estimativa técnica que VOCÊ assumiu — ex.: 'R13 = (5−2)/0,01 = 330Ω para o LED a 10 mA'"],
 "components": [
   {{"ref": "R1", "type": "{ENUM_TIPOS}",
    "value": "10k", "montagem": "THT|SMD", "quantidade": 5, "papel": "limitador do LED",
    "needs_review": false,
    "pins": [{{"number": "1"}}, {{"number": "2"}}]}},
   {{"ref": "U1", "type": "ci", "value": "RP2040 (QFN-56)", "montagem": "SMD",
    "papel": "controlador USB HID", "parts_hint": "",
    "pins": 56}}
 ],
 "connections": [
   {{"a": "U1.7", "b": "R1.1", "net_name": "DIS"}}
 ],
 "board_profile": {{"size_mm": {{"w": 50, "h": 30}}, "camadas": 1}}
}}"""


def _extrair_json(texto: str) -> dict | None:
    """JSON do corpo: aceita fence ```json ou objeto completo; None se não achou."""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", texto, re.DOTALL)
    bruto = m.group(1) if m else None
    if bruto is None:
        ini = texto.find("{")
        fim = texto.rfind("}")
        if ini >= 0 and fim > ini:
            bruto = texto[ini:fim + 1]
    if bruto is None:
        return None
    try:
        return json.loads(bruto)
    except json.JSONDecodeError:
        return None


def _prompt(pedido: str) -> str:
    return f"""Você é o engenheiro de aplicações do PCBForge. Converta o pedido abaixo num
RASCUNHO COMPLETO DE CIRCUITO que o usuário revisa e edita antes de fabricar
(revisão §13.1). Rascunho vazio ou esparso é FALHA SUA: decida pelo método-padrão
e entregue o circuito INTEIRO derivado — o usuário edita o que discordar.

PROCEDIMENTO DE PROJETO (vale para QUALQUER circuito — é método genérico,
NÃO uma lista de placas memorizadas):
1. Identifique a FUNÇÃO e os blocos: entrada (sensor/botão/teclado) →
   processamento (CI/microcontrolador) → saída (LED/relé/buzzer/motor) →
   alimentação → conectores (USB/borne/header).
2. Escolha peças padrão, comuns e baratas, JUSTIFICANDO cada uma no campo
   "papel".
3. Aplique os MÉTODOS-PADRÃO (suposições técnicas são SUAS — registre-as em
   "decisoes_padrao"; o usuário edita depois; NÃO as coloque em "omitido"):
   - LED individual: resistor série R = (Vcc − Vf) / I, I = 5–20 mA, valor
     comercial E24. Ex.: 5 V, vermelho (Vf≈2), 10 mA → R = 330Ω.
   - Matriz de teclas N×M: N pinos linha + M pinos coluna no CI; 1 diodo
     (1N4148) POR tecla contra ghosting; cada tecla é type "switch"
     (ex.: teclado 87 teclas → matriz ~14×7 + 87 diodos + CI com USB nativo).
   - Entrada digital (botão/switch/fim-de-curso): pull-up 10 kΩ type "resistor"
     para Vcc, contato fecha para GND.
   - Saída de potência (relé/motor/carga): type "transistor" ou type "mosfet"
     + resistor de base/gate (1–10 kΩ) + diodo flyback se carga indutiva.
   - Desacoplamento: 100 nF ("capacitor") por CI + eletrolítico de bulk por
     rail ("capacitor_polarizado", 10–100 µF).
   - Divisor de tensão: R1+R2; medida analógica (NTC/LDR): divisor com o
     sensor + RC de filtragem para o ADC.
   - CI com clock externo: type "cristal" + 2 capacitores 18–22 pF.
   - Alimentação por bateria/pilha: type "bateria" (holder) + diodo de
     proteção de polaridade; USB VBUS como alimentação direta.
   - Proteção na entrada de potência: type "fuse".
   - Alarme/aviso sonoro: type "buzzer" (+ transístor se corrente > 20 mA).
4. Derive TODAS as connections exigidas pela topologia (nets completas:
   linha↔coluna, diodos, CI↔matriz, USB VBUS/D+/D−, desacoplamento, pull-ups,
   GND) com endpoints EXATOS "Ref.pin". Net incompleta é FALHA SUA.
5. "omitido" fica APENAS para o que é decisão DO USUÁRIO e BLOQUEIA a revisão
   — MÁXIMO 3 perguntas (ex.: "MCU: RP2040 ou ATmega32U4?", "USB tipo C ou
   micro-B?"). Detalhe técnico derivável NÃO é omitido: decida e registre em
   "decisoes_padrao".

REGRAS OBRIGATÓRIAS (Plano Mestre §13.3):
- NUNCA invente componente: só use type/value genéricos conhecidos; se uma peça
  for específica (ex.: "ATmega328"), registre o papel parts_hint com LCSC C-code
  quando confiante, senão anote em "needs_review".
- Cada componente tem um "ref" PRÓPRIO e estável (R1, R2, C1, D1, U1, J1, SW1,
  Y1, Q1, F1, BZ1, BT1…); reutilize EXATAMENTE esse ref nas connections.
- "montagem": "THT" quando o pedido disser THT/perfuração/through-hole/borne de
  parafuso/LED 5mm/resistor axial; senão "SMD".
- CI: coloque o PACOTE no value (ex.: "LM386 (DIP-8)") e o nº de PINOS de forma
  COMPACTA: "pins": 32 (número) ou "pins": "1..32" — NÃO liste pino a pino.
- Peças REPETIDAS (teclas, diodos de matriz, LEDs): uma entrada por ref com o
  mesmo value (SW1, SW2… SW16; D1…D16) — liste todas, sem prosa entre elas.
- Potenciômetro é type "potenciometro" (3 pinos, 2 = cursor) — NUNCA "resistor".
- Derive TODAS as nets da topologia — cada connection precisa ter endpoints
  identificáveis; net incompleta é FALHA SUA, não silêncio.
- Todo endpoint de connection é EXATAMENTE "Ref.pin" com o NÚMERO real do pino
  (ex.: "U1.7", "R1.1") — nunca texto descritivo ("pino 7 do 555").
- Camadas: 1 a menos que a densidade justifique 2 (QFP/LQFP, matriz grande,
  trilhas cruzando demais). "size_mm": estime pela densidade e registre a
  estimativa em "decisoes_padrao" (pequeno ~50×30, médio ~80×50, grande
  ~100×70 mm).

SCHEMA (todos os campos, respeite os tipos):
{SCHEMA_HINT}

PEDIDO DO USUÁRIO:
\"\"\"{pedido}\"\"\""""


def interpretar(pedido: str) -> dict:
    """Pedido → (bruto|None, estados). análise via opencode headless.

    F14e: cadeia de fallback pelos modelos free — cota free é POR MODELO;
    quota estourada num modelo não trava o produto (tenta o próximo).
    """
    estados: list[str] = []
    agentes = ["opencode", "run", "--agent", "pcbforge-brain"]
    for modelo in MODELOS_FREE:
        tent = list(agentes)
        tent += ["-m", modelo, _prompt(pedido)]
        bruto, e = _executar(tent, modelo)
        estados += e
        if bruto is not None:
            estados.append(f"modelo:{modelo}")
            return bruto, estados
        if all("quota" not in x for x in e):
            # erro REAL (timeout/exit/JSON): não é de cota → não adianta cadeia
            return None, estados
    return None, estados + ["todos_modelos_quota_excedida"]


def _executar(args: list[str], modelo: str) -> tuple[dict | None, list[str]]:
    """Um chute do modelo (agent pcbforge-brain = ferramentas negadas)."""
    estados: list[str] = [f"tentativa:{modelo}"]
    try:
        from pcbforge import paths as _p
        r = subprocess.run(args, capture_output=True, text=True,
                           timeout=TIMEOUT_S, cwd=str(_p.tmp_dir()))
    except subprocess.TimeoutExpired:
        return None, estados + ["timeout"]
    saida = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0:
        saida_err = (r.stderr or "") + (r.stdout or "")
        if "Free usage limit" in saida_err or "usage limit" in saida_err.lower():
            estados.append("quota_free_excedida")   # diagnóstico honesto (§9)
        estados.append(f"opencode_exit_{r.returncode}")
        estados.append(saida_err[-200:])
        return None, estados
    bruto = _extrair_json(saida)
    if bruto is None:
        estados.append("json_invalido")
        estados.append(saida[-200:])
        return None, estados
    return bruto, estados


def _expande_pins(pins) -> list | None:
    """F14e — forma compacta do modelo → lista de pins real:
    32 / "32" / "1..32" / [{"number":"1..32"}] → [{"number":"1"}…{"number":"32"}].
    Listas de {"number": "n"} reais passam como estavam (nunca adivinhada)."""
    if isinstance(pins, int) and pins > 0:
        return [{"number": str(i)} for i in range(1, pins + 1)]
    if isinstance(pins, str):
        m = re.fullmatch(r"(\d+)\s*\.\.\s*(\d+)", pins.strip())
        if m:
            return [{"number": str(i)}
                    for i in range(int(m.group(1)), int(m.group(2)) + 1)]
        if pins.strip().isdigit():
            return [{"number": str(i)} for i in range(1, int(pins) + 1)]
    if isinstance(pins, list):
        out: list = []
        for p in pins:
            num = (p.get("number") if isinstance(p, dict) else p)
            m = re.search(r"(\d+)\s*\.\.\s*(\d+)", str(num))
            if m:
                out += [{"number": str(i)}
                        for i in range(int(m.group(1)), int(m.group(2)) + 1)]
            else:
                out.append(p if isinstance(p, dict) else {"number": str(num)})
        return out or pins
    return pins


def construir_sugestao(bruto: dict) -> dict:
    """Bruto do modelo → sugestão de netlist valizada (U-platform) com fonte.

    Cada componente recebe symbol/footprint do resolver APTO (F1); o que não
    resolver bem volta como needs_review (neca inventar — §13.3).
    """
    from pcbforge.parts.resolve import resolver, normalizar_tipo
    from pcbforge.core.validator import validar_netlist

    refs: dict[str, dict] = {}
    components: list[dict] = []
    tipo_ref: dict[str, int] = {}

    for c in bruto.get("components", []):
        tipo = normalizar_tipo(c.get("type"))          # F14e: sinônimo → canônico
        value = str(c.get("value") or "")
        part_hint = str(c.get("parts_hint") or c.get("part_hint") or "")
        pins_exp = _expande_pins(c.get("pins"))        # compacto → real ANTES
        sim, fp, src = resolver(tipo, value, part_hint,
                                montagem=str(c.get("montagem") or ""),
                                pins=len(pins_exp or []))
        if tipo in tipo_ref:
            tipo_ref[tipo] += 1
        else:
            tipo_ref[tipo] = 1
        ref_auto = ({"resistor": "R", "capacitor": "C", "capacitor_polarizado": "C",
                     "potenciometro": "RV", "led": "D", "diodo": "D", "conector": "J",
                     "ci": "U", "ic": "U", "timer": "U", "jumper": "JP",
                     "resistor_0r": "R0", "montadora": "H",
                     # F14e — types novos do vocabulário canônico
                     "switch": "SW", "cristal": "Y", "mosfet": "Q",
                     "transistor": "Q", "fuse": "F", "buzzer": "BZ",
                     "bateria": "BT"}.get(tipo, "X")
                    + str(tipo_ref[tipo]))
        ref = str(c.get("ref") or "").strip().upper() or ref_auto
        item = {"ref": ref, "type": tipo, "value": value,
                "symbol_ref": sim, "footprint_ref": fp, "source": src}
        pins = pins_exp
        if pins:
            item["pins"] = pins
        if src == "needs_review" or not fp or c.get("needs_review"):
            item["needs_review"] = True
        if c.get("papel"):
            item["papel"] = c["papel"]
        components.append(item)
        refs[ref] = item

    connections = []
    for conn in bruto.get("connections", []):
        a = _pin_resolver(conn.get("a"), refs)
        b = _pin_resolver(conn.get("b"), refs)
        if a and b:
            connections.append({
                "a": {"ref": a[0], "pin": a[1]},
                "b": {"ref": b[0], "pin": b[1]},
                "net_name": conn.get("net_name") or "NET_NOME_FALTANDO",
                "needs_review": bool(conn.get("needs_review") or a[2] or b[2]),
            })

    perfil = {"name": "sugestao-brain",
              "size_mm": dict(bruto.get("board_profile", {}).get("size_mm") or {"w": 50, "h": 30}),
              "camadas": int(bruto.get("board_profile", {}).get("camadas") or 1)}
    erros = validar_netlist({"components": components,
                             "connections": connections,
                             "rails": (bruto.get("rails") or [])})
    erros_bloqueio = [p for p in erros if p.get("severidade") == "erro"]
    # F14e — cap de perguntas BLOQUEANTES (§F14e): tudo além de 3 vira decisão-
    # padrão (o modelo não pode esvaziar o rascunho virando questionário).
    omitido = [str(x).strip() for x in (bruto.get("omitido") or []) if str(x).strip()]
    if len(omitido) > 3:
        exced = omitido[3:]
        omitido = omitido[:3]
        erros.append({"codigo": "OMITIDO_CAP", "severidade": "warning",
                      "mensagem": (f"{len(exced)} dúvida(s) excederam o cap de 3 "
                                   "perguntas bloqueantes e viraram decisão-padrão "
                                   "(revise na §13.1): ")
                                   + "; ".join(exced)[:300]})
    decisoes = [str(x).strip() for x in (bruto.get("decisoes_padrao") or [])
                if str(x).strip()]
    return {"components": components, "connections": connections,
            "omitido": omitido, "decisoes_padrao": decisoes, "perfil": perfil,
            "validador": erros, "bloqueios": erros_bloqueio}


def _pin_resolver(endpoint, refs: dict[str, dict]) -> tuple[str, str, bool] | None:
    """'R1.2' / 'R1 2' / 'R1' → (ref, pin|'?', needs_review). Nunca adivinha."""
    needs = False
    texto = str(endpoint or "").strip()
    if (not texto) or ("?" in texto) or ("omit" in texto.lower()):
        return None
    m = re.fullmatch(r"([A-Za-z]\w*)[.\s#]*(\d+|[A-Z]+)?", texto)
    if not m:
        return None
    ref = None
    if m.group(1).upper() in refs:
        ref = m.group(1).upper()
    pin = m.group(2) or "?"
    if ref is None:                                 # papel genérico sem ref clara
        needs = True
        ref = next(iter(refs), None)
    return (ref, pin, needs)


def propor_previa(sugestao: dict) -> str:
    """Texto de conferência (§5.3) — o usuário aprova antes de gerar."""
    linhas = ["Prévia da netlist proposta — REVISE antes de gerar:"]
    linhas.append("components:")
    for c in sugestao["components"]:
        marca = " ⚠️NEEDS_REVIEW" if c.get("needs_review") else ""
        linhas.append(f"  {c['ref']:<4} {c['type']:<12} {c['value']:<12} "
                      f"→ {c['footprint_ref'] or '(sem footprint)'}{marca}")
    linhas.append("connections:")
    for cn in sugestao["connections"]:
        marca = " ⚠️" if cn.get("needs_review") else ""
        linhas.append(f"  {cn['a']['ref']}.{cn['a']['pin']} ↔ "
                      f"{cn['b']['ref']}.{cn['b']['pin']}  net: {cn['net_name']}{marca}")
    if sugestao.get("decisoes_padrao"):
        linhas.append("decisões-padrão assumidas (EDITÁVEIS na revisão): "
                      + "; ".join(map(str, sugestao["decisoes_padrao"])))
    if sugestao["omitido"]:
        linhas.append("pendentes de resposta do usuário: " + "; ".join(map(str, sugestao["omitido"])))
    if sugestao["validador"]:
        linhas.append(f"validador: {len(sugestao['validador'])} problema(s)")
    return "\n".join(linhas)

"""parts.resolve — mapeia (type, value, part_hint) → símbolo/footprint das libs oficiais KiCad.

Regra do Plano Mestre §6.1: 1ª opção é a biblioteca oficial KiCad (offline).
Aqui fica a tabela de defaults por tipo + busca direta nos .kicad_sym oficiais.
"""
from __future__ import annotations

import re
from pathlib import Path

from pcbforge import paths

_sh = paths.kicad_shared() or Path("kicad_shared_nao_encontrado")
SYMBOLS_DIR = _sh / "symbols"
FOOTPRINTS_DIR = _sh / "footprints"
MODELS3D_DIR = _sh / "3dmodels"

# Defaults por type (Plano Mestre §12.2 P01: resistor → Device:R + R_0603)
DEFAULTS: dict[str, dict[str, str]] = {
    "resistor": {"symbol": "Device:R", "footprint": "Resistor_SMD:R_0603_1608Metric"},
    "capacitor": {"symbol": "Device:C", "footprint": "Capacitor_SMD:C_0603_1608Metric"},
    "capacitor_polarizado": {"symbol": "Device:C_Polarized", "footprint": "Capacitor_SMD:CP_Elec_6.3x5.9"},
    "indutor": {"symbol": "Device:L", "footprint": "Inductor_SMD:L_0603_1608Metric"},
    "led": {"symbol": "Device:LED", "footprint": "LED_SMD:LED_0603_1608Metric"},
    "diodo": {"symbol": "Device:D", "footprint": "Diode_SMD:D_SOD-123"},
    "jumper": {"symbol": "Jumper:Jumper_2_Bridged", "footprint": "Resistor_SMD:R_0603_1608Metric"},
    "resistor_0r": {"symbol": "Device:R", "footprint": "Resistor_SMD:R_0603_1608Metric"},
    "conector": {"symbol": "Connector_Generic:Conn_01x02", "footprint": "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical"},
    "montadora": {"symbol": "não tem", "footprint": "MountingHole:MountingHole_3.2mm_M3"},
    # F14e — tipos canônicos expandidos (método genérico do brain, §22.4 P1→F14e).
    # §19.2: cada footprint abaixo foi provado APTO no disco (pads + .step)
    # antes de entrar no enum (prova 02-11: catalogo.apto() — switch B3U,
    # cristal 3225, SOT-23, fuse 1206, buzzer TDK, holder 18650).
    "switch": {"symbol": "Switch:SW_Push", "footprint": "Button_Switch_SMD:SW_SPST_B3U-1000P"},
    "cristal": {"symbol": "Device:Crystal", "footprint": "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm"},
    "mosfet": {"symbol": "Device:Q_NMOS", "footprint": "Package_TO_SOT_SMD:SOT-23"},
    "transistor": {"symbol": "Device:Q_NPN", "footprint": "Package_TO_SOT_SMD:SOT-23"},
    "fuse": {"symbol": "Device:Fuse", "footprint": "Fuse:Fuse_1206_3216Metric"},
    "buzzer": {"symbol": "Device:Buzzer", "footprint": "Buzzer_Beeper:Buzzer_TDK_PS1240P02BT_D12.2mm_H6.5mm"},
    "bateria": {"symbol": "Device:Battery", "footprint": "Battery:BatteryHolder_Keystone_1042_1x18650"},
}

# Defaults THT (F7 — pedido do usuário em montagem por perfuração). Todos
# verificados aptos no catalogo.json (prova 2026-10-28: golden I04 NE555).
DEFAULTS_THT: dict[str, dict[str, str]] = {
    "resistor": {"symbol": "Device:R", "footprint": "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal"},
    "capacitor": {"symbol": "Device:C", "footprint": "Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P2.50mm"},
    "capacitor_polarizado": {"symbol": "Device:C_Polarized", "footprint": "Capacitor_THT:CP_Radial_D5.0mm_P2.50mm"},
    "indutor": {"symbol": "Device:L", "footprint": "Inductor_THT:L_Axial_L6.6mm_D2.7mm_P7.62mm_Horizontal"},
    "led": {"symbol": "Device:LED", "footprint": "LED_THT:LED_D5.0mm"},
    "diodo": {"symbol": "Device:D", "footprint": "Diode_THT:D_DO-35_SOD27_P7.62mm_Horizontal"},
    "resistor_0r": {"symbol": "Device:R", "footprint": "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal"},
    "conector": {"symbol": "Connector_Generic:Conn_01x02", "footprint": "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2_1x02_P5.00mm_Horizontal"},
    # potenciômetro (I05 — VR1 do LM386): 3 pinos, pino 2 = cursor
    "potenciometro": {"symbol": "Device:R_Potentiometer", "footprint": "Potentiometer_THT:Potentiometer_Bourns_3296W_Vertical"},
    # novos tipos F14e, variante THT (prova APTO no disco 02-11: PUSH_6mm,
    # HC49-U, TO-92_Inline, Bulgin 5x20, buzzer RM7.6, holder AA)
    "switch": {"symbol": "Switch:SW_Push", "footprint": "Button_Switch_THT:SW_PUSH_6mm"},
    "cristal": {"symbol": "Device:Crystal", "footprint": "Crystal:Crystal_HC49-U_Vertical"},
    "mosfet": {"symbol": "Device:Q_NMOS", "footprint": "Package_TO_SOT_THT:TO-92_Inline"},
    "transistor": {"symbol": "Device:Q_NPN", "footprint": "Package_TO_SOT_THT:TO-92_Inline"},
    "fuse": {"symbol": "Device:Fuse", "footprint": "Fuse:Fuseholder_Cylinder-5x20mm_Bulgin_FX0456_Vertical_Closed"},
    "buzzer": {"symbol": "Device:Buzzer", "footprint": "Buzzer_Beeper:Buzzer_12x9.5RM7.6"},
    "bateria": {"symbol": "Device:Battery", "footprint": "Battery:BatteryHolder_Keystone_103_1x20mm"},
}

# Overrides por palavras-chave do `value` (técnicas, econômicas)
# ATENÇÃO (lição F14e 02-11): a checagem é `chave in val` com val MINÚSCULO —
# chave maiúscula NUNCA casa (o override USB antigo era morto sem sinais).
_OVERRIDES_VALUE: list[tuple[str, str, str]] = [
    # (palavra-chave no value, symbol, footprint)
    # ESP32 THT/SMD (I05 — semáforo do usuário): módulo com 3D real APTO no catálogo
    # ESP32-C3 (F14c — golden semaforo): módulo castelado com 3D real APTO.
    # §20.2 do Plano Mestre — binding aprovado na prévia §5.1; a variante
    # oficial RF_Module:ESP32-C3-MINI-1 NÃO tem 3D, logo proibida.
    # Deve vir ANTES ("esp32", ...): a checagem é `chave in val`.
    ("esp32-c3", "Espressif:ESP32-C3-MINI-1", "Espressif:ESP32-C3-MINI-1"),
    ("esp32", "RF_Module:ESP32-WROOM-32", "RF_Module:ESP32-WROOM-32"),
    ("atmega328", "MCU_Microchip_ATmega:ATmega328P-AU", "Package_QFP:TQFP-32_7x7mm_P0.8mm"),
    # USB substituiu "conector" genérico: receptáculo C real APTO (prova 02-11)
    ("usb", "Connector:USB_C_Receptacle_USB2.0", "Connector_USB:USB_C_Receptacle_Amphenol_12401610E4-2A"),
    # diodo Zener escrito no value (ex.: "diodo zener 5V1") → símbolo certo
    ("zener", "Device:D_Zener", "Diode_SMD:D_SOD-123"),
    # NE555 THT (F7 — golden I04): símbolo Timer:NE555P + DIP-8 7,62mm
    ("ne555", "Timer:NE555P", "Package_DIP:DIP-8_W7.62mm"),
    # LM386 THT (I05 — pedido do usuário): símbolo oficial DIP-8
    ("lm386", "Amplifier_Audio:LM386", "Package_DIP:DIP-8_W7.62mm"),
    # Arduino Nano: não existe símbolo oficial → entra como needs_review
    # e o cérebro pergunta ao usuário qual módulo/placa empregar.
]

# F14e — vocabulário canônico do produto (método geral, NÃO placas soltas).
# O enum que o prompt do brain usa E a normalização de sinônimos vêm daqui:
# fonte única de verdade para o que o resolver resolve APTO.
TIPOS_CANONICOS: list[str] = [
    "resistor", "potenciometro", "capacitor", "capacitor_polarizado",
    "indutor", "led", "diodo", "conector", "ci", "jumper", "resistor_0r",
    "switch", "cristal", "mosfet", "transistor", "fuse", "buzzer",
    "bateria", "montadora",
]

# sinônimos → tipo canônico (o pedido do usuário chega em linguagem natural:
# "tecla", "botão", "chave tátil", "pilha", "fusível"… todos viram o tipo
# canônico e caem no resolver APTO — nunca needs_review por sinônimo).
_ALIASES_TIPO: dict[str, str] = {
    # switch / chave / botão / tecla
    "switch": "switch", "chave": "switch", "botao": "switch", "botão": "switch",
    "botões": "switch", "botones": "switch", "tecla": "switch", "teclas": "switch",
    "tact": "switch", "tactile": "switch", "push": "switch", "contato": "switch",
    # cristal
    "cristal": "cristal", "crystal": "cristal", "quartz": "cristal",
    "xtal": "cristal", "oscilador": "cristal",
    # mosfet / transistor
    "mosfet": "mosfet", "mos": "mosfet", "fet": "mosfet", "jfet": "mosfet",
    "igbt": "mosfet",
    "transistor": "transistor", "npn": "transistor", "pnp": "transistor",
    "bjt": "transistor", "tr": "transistor",
    "qnpn": "transistor", "transistores": "transistor",
    # fuse / buzzer / bateria
    "fuse": "fuse", "fusivel": "fuse", "fusível": "fuse", "fuzivel": "fuse",
    "buzzer": "buzzer", "beeper": "buzzer", "campainha": "buzzer",
    "altifalante": "buzzer", "speaker": "buzzer",
    "bateria": "bateria", "pilha": "bateria", "pilhas": "bateria",
    "battery": "bateria", "acumulador": "bateria", "lition": "bateria",
    # ci aliases vivos mantidos do resolver antigo
    "ic": "ci", "timer": "ci", "mcu": "ci", "microcontrolador": "ci",
    "microcontroladora": "ci", "processador": "ci",
}


def normalizar_tipo(tipo: str) -> str:
    """Sinônimo → tipo canônico (lower/trim/alias); devolve entrada se desconhecida."""
    t = (tipo or "").strip().lower()
    return _ALIASES_TIPO.get(t, t)


def _conector(val: str, tht: bool, pins: int) -> tuple[str, str, str]:
    """Conector genérico 1×N — o N vem do nº de pins (família APENAS genérica,
    §13.3: Connector_*_Generic/HEADER, nunca modulo de placa). Borne/parafuso
    → Phoenix MKDS P5.0; senão header 2,54 (THT convenção I04/I05).
    """
    nn = pins if (pins and 1 <= pins <= 20) else 0
    if not nn:
        m = re.search(r"(\d+)\s*(?:pinos?|vias)\b", val)
        if not m:
            m = re.search(r"1\s*[x×]\s*(\d+)", val)
        if m and 1 <= int(m.group(1)) <= 20:
            nn = int(m.group(1))
    nn = nn or 2
    if nn < 2:
        nn = 2                                  # pino único → header 1x02 mínimo
    if tht or "borne" in val or "parafuso" in val:
        fp = (f"TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-{nn}"
              f"_1x{nn:02d}_P5.00mm_Horizontal")
    else:
        fp = f"Connector_PinHeader_2.54mm:PinHeader_1x{nn:02d}_P2.54mm_Vertical"
    fp2 = _filtrar_aptos(fp)
    if fp2:
        return (f"Connector_Generic:Conn_01x{nn:02d}", fp2, "kicad-library")
    return ("", "", "needs_review")


def resolver(type_: str, value: str = "", part_hint: str = "",
             montagem: str = "", pins: int = 0) -> tuple[str, str, str]:
    """Devolve (symbol_ref, footprint_ref, fonte).

    Regras:
      1. part_hint com 'C' LCSC → (deferred para parts/lcsc — retorna ("", "", "lcsc"))
      2. override por value
      3. default por type (THT quando montagem="THT" — F7; capacitor com valor
         em µF é polarizado — eletrolítico — mesmo sem type explícito, mas
         NÃO se o texto disser cerâmico/np0/c0g/disc)
      4a. tipo 'ci'/'ic'/'timer' sem override → inferência de pacote
         (DIP-8/SOIC/LQFP no value) + busca do MPN nos .kicad_sym oficiais
      4b. se tipo desconhecido → NEEDS_REVIEW ("", "", "needs_review")

    Regra F1 (Plano Mestre §17): o footprint devolvido TEM de estar apto no
    catálogo (pads claros + .step no disco; exceção MountingHole). Se o default
    não estiver apto, troca pela alternativa mais parecida da mesma lib; sem
    alternativa → needs_review (nunca inventa componente — §13.3).
    """
    hint = (part_hint or "").strip()
    val = (value or "").strip().lower()
    tipo = normalizar_tipo(type_)                          # F14e: sinônimos → canônico
    # potenciômetro escrito como resistor ("Potenciômetro de 10 kΩ")
    if "potenci" in tipo or "potenci" in val:
        tipo = "potenciometro"
    tht = (montagem or "").strip().upper().startswith("THT")
    if tipo == "capacitor" and re.search(r"[\d,.]+\s*[uµ]f", val) \
            and not re.search(r"cer[aâ]mi|npo|c0g|np0|disc|mkt", val, re.I):
        tipo = "capacitor_polarizado"                        # 10µF ⇒ eletrolítico

    if hint.startswith("C") and hint[1:].isdigit():          # regra nº 1
        return ("", "", "lcsc")
    for chave, sym, fp in _OVERRIDES_VALUE:                   # regra nº 2
        if chave in val:
            fp2 = _filtrar_aptos(fp)
            if fp2 is None:
                return ("", "", "needs_review")
            return (sym, fp2, "override")
    if tipo in ("ci",):                                       # regra 4a (CI genérico)
        return _resolver_ci(val, tht, pins)
    if tipo == "conector":                                    # F14e: 1×N genérico
        return _conector(val, tht, pins)
    if tht and tipo in DEFAULTS_THT:                          # regra nº 3 (THT — F7)
        d = DEFAULTS_THT[tipo]
        fp2 = _filtrar_aptos(d["footprint"])
        if fp2 is None:
            return ("", "", "needs_review")
        return (d["symbol"], fp2, "kicad-library-tht")
    if tipo in DEFAULTS:                                      # regra nº 3
        d = DEFAULTS[tipo]
        fp2 = _filtrar_aptos(d["footprint"])
        if fp2 is None:
            return ("", "", "needs_review")
        return (d["symbol"], fp2, "kicad-library")
    return ("", "", "needs_review")                           # regra nº 4b


def _resolver_ci(val: str, tht: bool, pins: int = 0) -> tuple[str, str, str]:
    """CI sem override: infere o pacote (DIP/SOIC/LQFP/TQFP/SOT/TO-92) pelo value
    OU pelo nº de pinos, e procura a variante apta no catálogo (F1). Símbolo
    oficial é buscado pelo MPN; sem símbolo → needs_review do footprint inferido
    (o usuário confere no revisor §13.1 — nunca inventa componente, §13.3).
    """
    from pcbforge.parts import catalogo
    fam, npins = _pacote_no_value(val)
    if not fam:
        fam, npins = _fam_por_pinos(pins, tht), str(pins) if pins else ""
    if not npins:
        return ("", "", "needs_review")
    prefixo = {"DIP": "Package_DIP:DIP-", "SOIC": "Package_SO:SOIC-",
               "LQFP": "Package_QFP:LQFP-", "TQFP": "Package_QFP:TQFP-",
               "SOT223": "Package_TO_SOT_SMD:SOT-223",
               "SOT23": "Package_TO_SOT_SMD:SOT-23-",
               "TO92": "Package_TO_SOT_THT:TO-92_"}[fam]
    # variante mais simples primeiro (plain antes de -1EP/socket): nome mais curto
    aptos = sorted((k for k in catalogo.carregar()
                    if k.startswith(f"{prefixo}{npins}") and catalogo.apto(k)),
                   key=lambda k: (len(k), k)) if fam not in ("SOT223",) else \
        sorted((k for k in catalogo.carregar()
                if k.startswith(prefixo) and catalogo.apto(k)),
               key=lambda k: (len(k), k))
    if not aptos:
        return ("", "", "needs_review")
    fp = aptos[0]
    mpn = re.match(r"[a-z0-9.\-]+", val)
    # busca por símbolo só faz sentido com MPN real (letras+dígitos com número)
    sym = _busca_simbolo(mpn.group(0)) if mpn and re.search(r"\d", mpn.group(0)) else None
    if sym:
        return (sym, fp, "kicad-library")
    return ("", fp, "needs_review")


def _pacote_no_value(val: str) -> tuple[str, str]:
    """Procura o pacote no texto (lowercase) → (fam, npins) ou ('', '')."""
    m = re.search(r"(SOT-23)-?(\d{1,2})?", val)
    if m:
        return ("SOT23", m.group(2) or "3")
    if "sot-223" in val:
        return ("SOT223", "3")
    if "to-92" in val:
        return ("TO92", "3")
    m = re.search(r"(DIP|SOIC|LQFP|TQFP)-?\s?(\d{1,2})", val, re.I)
    if m:
        return (m.group(1).upper(), m.group(2))
    return ("", "")


def _fam_por_pinos(pins: int, tht: bool) -> str:
    """Família de pacote por nº de pinos (inferência honesta, §6.1)."""
    if not pins:
        return "DIP"
    if tht and pins <= 64:
        return "DIP"
    return "LQFP" if pins > 48 else "SOIC"


def _busca_simbolo(mpn: str) -> str | None:
    """Procura `(symbol "MPN*"` nos .kicad_sym oficiais → 'Lib:MPN*' ou None.
    Case-insensitive e POR PREFIXO: 'ams1117-3.3' casa o oficial 'AMS1117-3.3'.
    Sub-drawings (`X_0_1`) são descartados — só símbolos reais (§13.3).
    """
    cache = _busca_simbolo.__dict__.setdefault("cache", {})
    if mpn in cache:
        return cache[mpn] or None
    cache[mpn] = ""
    padrao = re.compile(rf'symbol "([A-Za-z0-9_\-\.]+)"', re.I)
    melhor = None
    for frente in sorted(SYMBOLS_DIR.glob("*.kicad_sym")):
        texto = frente.read_text(encoding="utf-8")
        for m in padrao.finditer(texto):
            nome = m.group(1)
            if re.search(r"_\d+_\d+$", nome):
                continue                              # sub-drawing, não símbolo
            if not nome.lower().startswith(mpn):
                continue
            exato = nome.lower() == mpn
            cand = (frente.stem, nome)
            if melhor is None or exato or (not melhor[2] and len(nome) < len(melhor[1])):
                melhor = (cand[0], nome, exato)
                if exato:
                    break
        if melhor and melhor[2]:
            break
    if melhor:
        lib = f"{melhor[0]}:{melhor[1]}"
        cache[mpn] = lib
        return lib
    return None


def _filtrar_aptos(footprint_ref: str) -> str | None:
    """Converte footprint → versão apta do catálogo (F1, Plano Mestre §17).

    Devolve o próprio footprint se já apto; a melhor alternativa da mesma lib
    caso o original não seja; None se não há alternativa verificada (o chamador
    marca needs_review — nunca inventa componente, §13.3).
    """
    from pcbforge.parts import catalogo

    if catalogo.apto(footprint_ref):
        return footprint_ref
    alt = catalogo.melhor_alternativa(footprint_ref)
    # alternativa TEM de ser verificada de novo (mesma lib, família parecida)
    return alt if (alt and catalogo.apto(alt)) else None

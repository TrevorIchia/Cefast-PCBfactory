"""generator.schematic — netlist neutra → .kicad_sch (função `gerar_esquematico`).

Regras do Plano Mestre §7:
  - símbolos VEM DA BIBLIOTECA (nunca digitados)
  - rótulos de net preferidos sobre fios longos
  - power rails viram global labels
  - refs coerentes entre esquemático e PCB
"""
from __future__ import annotations

import os
import re
from pathlib import Path

# A biblioteca kicad-sch-api descobre symbols via variável de ambiente.
# Deve ser definida ANTES do import — nunca apagar o que o usuário definiu.
# F14a/F14c: a lib EXTRA do repositório (libcache/kicad-extra/symbols — Espressif
# etc.) entra AQUI, porque bindings tipo Espressif:ESP32-C3-MINI-1 estão fora
# da lib oficial. kicad-sch_api aceita caminhos separados por os.pathsep
# (library/cache.py:1166 — ": for Unix, ; for Windows").
_extra = Path(__file__).resolve().parent.parent.parent / "libcache/kicad-extra/symbols"
_oficial = "/Applications/KiCad.app/Contents/SharedSupport/symbols"
_paths_env = [_p for _p in os.environ.get("KICAD_SYMBOL_DIR", "").split(os.pathsep) if _p]
if not _paths_env:
    _paths_env = [_oficial]
if _extra.is_dir() and str(_extra) not in _paths_env:
    _paths_env.append(str(_extra))
os.environ["KICAD_SYMBOL_DIR"] = os.pathsep.join(_paths_env)

import kicad_sch_api as ksa  # noqa: E402  (import precisa vir depois do setdefault)

KICAD_CLI = "/Applications/KiCad.app/Contents/MacOS/kicad-cli"
RAILS_PADRAO = {"VBUS", "GND", "VIN", "VCC", "+5V", "+3V3", "GNDA", "GND_PWR"}

_PASSO_X = 30.0   # espaçamento horizontal entre componentes
_PASSO_Y = 22.0   # espaçamento vertical entre blocos

# Bug do kicad-sch-api (upstream): serializa `(alternate NAME ...)` SEM aspas
# no nome — o parser do KiCad rejeita e o kicad-cli morre com "Houve uma
# falha ao ler o esquemático" (prova: STM32F103C8Tx, 36 alternates, 28-10).
_RE_ALTERNATE_SEM_ASPAS = re.compile(r'\(alternate\s+([A-Za-z0-9_.\-]+)')


def _fixar_alternates(sch_path: Path) -> int:
    """Re-quotinha os nomes de `(alternate ...)` que a kicad-sch-api desquotou."""
    txt = sch_path.read_text(encoding='utf-8')
    novo, n = _RE_ALTERNATE_SEM_ASPAS.subn(r'(alternate "\1"', txt)
    if n:
        sch_path.write_text(novo, encoding='utf-8')
    return n


def _fixar_properties_private(sch_path: Path) -> int:
    """Remove `(property private ...)` dos símbolos embutidos no lib_symbols.

    Bug do kicad-sch-api (upstream): as propriedades PRIVATE da lib (notas
    KLC_S3.3/KLC_S4.1 — documentação, sem função elétrica) são re-serializadas
    malformadas: `(property "private" "KLC_S3.3" texto-sem-aspas ...)` — a
    chave `private` vai pro lugar do NOME e o valor fica solto, e o parser do
    KiCad rejeita o arquivo inteiro ("Houve uma falha ao ler o esquemático";
    prova por bissecção 28-10: Crystal_GND24 isolado rc=3, -=6º filho; resto
    dos símbolos rc=0). Fix: remover o bloco inteiramente (nota de lib).
    """
    txt = sch_path.read_text(encoding='utf-8')
    n = 0
    while (i := txt.find('(property "private"')) >= 0:
        # fim do bloco balanceado
        prof = 0
        fim = len(txt)
        for j in range(i, len(txt)):
            if txt[j] == '(':
                prof += 1
            elif txt[j] == ')':
                prof -= 1
                if prof == 0:
                    fim = j + 1
                    break
        txt = txt[:i] + txt[fim:]
        n += 1
    if n:
        sch_path.write_text(txt, encoding='utf-8')
    return n


def _origem_componente(i: int) -> tuple[float, float]:
    """Grade simples: 2 colunas, linha a cada passo."""
    col = i % 2
    lin = i // 2
    return (90 + col * _PASSO_X, 60 + lin * _PASSO_Y)


def gerar_esquematico(netlist: dict, pasta_kicad: Path, nome_proj: str) -> Path:
    """Cria .kicad_sch a partir da netlist neutra. Falha com exceção legível."""
    if not netlist.get("components"):
        raise ValueError("netlist sem componentes (bloqueio de geração — ver U01 do plano)")

    sch = ksa.create_schematic(name=nome_proj)

    refs: dict[str, tuple[float, float]] = {}
    for i, comp in enumerate(netlist["components"]):
        ref = comp["ref"]
        sym = comp.get("symbol_ref", "")
        if not sym or sym == "needs_review":
            raise ValueError(f"componente {ref} sem symbol_ref resolvido (NEEDS_REVIEW)")
        try:
            sch.components.add(
                lib_id=sym,
                reference=ref,
                value=comp.get("value", ""),
                footprint=comp.get("footprint_ref") or None,
                position=_origem_componente(i),
            )
        except Exception as e:  # noqa: BLE001 — mensagem clara p/ o cérebro
            raise ValueError(f"falha ao adicionar {ref} ({comp.get('value')}): biblioteca de símbolo '{sym}' não encontrada — {e}") from e
        refs[ref] = _origem_componente(i)

    # Conexões: wire entre pinos; rail nomeada pega global label na ponta
    for conn in netlist.get("connections", []):
        a, b = conn["a"], conn["b"]
        try:
            sch.connect_pins_with_wire(a["ref"], str(a["pin"]), b["ref"], str(b["pin"]))
        except Exception as e:  # noqa: BLE001
            raise ValueError(f"conexão impossível {a['ref']}:{a['pin']} <-> {b['ref']}:{b['pin']}: {e}") from e

        nome_net = conn.get("net_name", "")
        if nome_net in RAILS_PADRAO:
            pa = sch.get_component_pin_position(a["ref"], str(a["pin"]))
            pb = sch.get_component_pin_position(b["ref"], str(b["pin"]))
            escolhido = (pa.x < pb.x and (a["ref"], a["pin"])) or (a["ref"], a["pin"])
            # label na ponta do pino mais à esquerda
            pmin = pa if pa.x <= pb.x else pb
            sch.add_global_label(text=nome_net, position=(pmin.x, pmin.y), shape="input")
        elif nome_net:
            pa = sch.get_component_pin_position(a["ref"], str(a["pin"]))
            pb = sch.get_component_pin_position(b["ref"], str(b["pin"]))
            pmin = pa if pa.x <= pb.x else pb
            sch.add_global_label(text=nome_net, position=(pmin.x, pmin.y), shape="passive")

    os.makedirs(pasta_kicad, exist_ok=True)
    saida = pasta_kicad / f"{nome_proj}.kicad_sch"
    sch.save(str(saida))
    n_alt = _fixar_alternates(saida)
    n_priv = _fixar_properties_private(saida)
    if n_alt or n_priv:
        pass  # bugs da kicad-sch-api corrigidos pós-save — silencioso
    return saida


def exportar_netlist_kicad(sch_path: Path) -> dict[str, dict[str, str]]:
    """Gera netlist via kicad-cli e devolve {ref: {pin: net}} p/ conferência."""
    import re
    import subprocess
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".net", delete=False) as tmp:
        destino = tmp.name
    r = subprocess.run([KICAD_CLI, "sch", "export", "netlist", str(sch_path), "-o", destino],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"kicad-cli netlist falhou: {r.stderr[:300] if r.stderr else 'sem stderr'}")
    txt = Path(destino).read_text(encoding="utf-8")

    mapeamento: dict[str, dict[str, str]] = {}
    # Pega cada "(net (code ...)" e recorta o bloco inteiro por profundeza de parênteses
    for inicio in re.finditer(r'\(net\n\s*\(code', txt):
        i = txt.rindex("(net", 0, inicio.end())
        prof, j = 0, i
        while j < len(txt):
            if txt[j] == "(":
                prof += 1
            elif txt[j] == ")":
                prof -= 1
                if prof == 0:
                    break
            j += 1
        bloco = txt[i:j]
        m_net = re.search(r'\(name "([^"]+)"\)', bloco)
        if not m_net:
            continue
        nome_net = m_net.group(1)
        for par in re.finditer(r'\(node\s*\(ref "(\w+)"\)\s*\(pin "(\w+)"\)', bloco, re.S):
            mapeamento.setdefault(par.group(1), {})[par.group(2)] = nome_net
    if not mapeamento:
        raise RuntimeError("netlist gerada sem nodes (formato inesperado)")
    return mapeamento

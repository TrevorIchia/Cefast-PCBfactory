"""gui.app — GUI web do PCBForge (F3 — M9, Plano Mestre §17).

FastAPI + um `index.html` — sem node/npm. Regras §13 cumpridas:
  §13.1 revisão do netlist na tela (validação viva pontuada),
  §13.2 revisão do perfil na tela (validação viva),
  §13.8 nomes em [A-Za-z0-9-] (proteção de path),
  build.log sempre gravado e visível (streaming por polling).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from pcbforge import paths

ROOT = Path(__file__).resolve().parents[2]
GUI_DIR = Path(__file__).resolve().parent

_estados_build: dict[str, dict] = {}
_lock = threading.Lock()
# F14e — cache da ÚLTIMA sugestão por pedido: o /criar REAPROVEITA o rascunho
# que o usuário viu na prévia (antes re-chamava o modelo e uma segunda
# interpretação vazia disparava o U00 fantasma "netlist sem componentes").
_cache_sugestao: dict[str, dict] = {}


def _bloqueio_criacao(sugestao: dict) -> list[str]:
    """Gate da criação (§F14e): o draft é revisável na §13.1 — a ÚNICA coisa
    que bloqueia é rascunho REALMENTE vazio (U00). Needs_review, omitido e
    warnings passam (o gate de EXPORT §13 continua intacto lá no build)."""
    if not (sugestao.get("components") or []):
        return ["U00: rascunho sem componentes — o brain não entregou o circuito "
                "(completo). Reformule o pedido com mais detalhes (função, "
                "alimentação, conectores)."]
    return []


def _placa(nome: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9-]+", nome) or not nome:
        raise HTTPException(400, f"nome '{nome}' fora de [A-Za-z0-9-] (§13.8)")
    pasta = ROOT / "boards" / nome
    if not pasta.is_dir():
        raise HTTPException(404, f"projeto '{nome}' não existe")
    return pasta


API = FastAPI(title="PCBForge", version="1.0.0-m3")


@API.get("/", response_class=HTMLResponse)
def index() -> FileResponse:
    return FileResponse(GUI_DIR / "index.html")


@API.get("/api/saude")
def saude() -> dict:
    return {"ok": True}


@API.post("/api/brain")
def brain_endpoint(corpo: dict) -> dict:
    """Pedido em linguagem natural → sugestão revisável (F4 — M10, §5/§13.3)."""
    from pcbforge import brain as cb
    pedido = str(corpo.get("pedido") or "").strip()
    if not pedido:
        raise HTTPException(400, "campo 'pedido' vazio")
    bruto, estados = cb.interpretar(pedido)
    if bruto is None:
        return {"estados": estados, "bruto": None}
    sugestao = cb.construir_sugestao(bruto)
    if len(_cache_sugestao) > 20:                 # cache pequeno: só o último ciclo
        _cache_sugestao.pop(next(iter(_cache_sugestao)))
    _cache_sugestao[pedido] = sugestao
    return {"estados": estados, "previa": cb.propor_previa(sugestao), "sugestao": sugestao}


def _yaml_do_perfil(nome: str, pedido: str, camadas: int, size: dict) -> str:
    """board_profile.yaml com os defaults do §4.2 (FR4, 1oz, verde 1.6mm)."""
    fl = lambda v: float(v)  # noqa: E731 — formatação de float no YAML
    return (f"name: {nome}\nstackup:\n  layers: {camadas}\n"
            "  board_material: FR4\n"
            "  copper_oz: 1.0\n  thickness_mm: 1.6\n  color: green\n"
            "  silkscreen: white\ngold_fingers: false\n"
            f"size_mm: {{w: {fl(size.get('w', 50))}, h: {fl(size.get('h', 30))}}}\n"
            "outline_shape: retângulo\n"
            "mounting: {diameter_mm: 3.2, corners: 4, margin: 3}\n"
            "min_trace_mm: 0.25\nmin_clearance_mm: 0.25\nmin_via_mm: 0.5\n"
            "high_current_traces: []\n"
            "autoroute: {timeout_s: 600, tentativas: 3, otimizacao_iteracoes: 600}\n"
            "assembly_jlcpcb: false\nthermal_reliefs: true\n"
            f"notes: 'pedido (§5.1): {pedido[:120]}'\n")


@API.post("/api/brain/criar")
def brain_criar(corpo: dict) -> dict:
    """Aprovação do usuário (§5.1 passo 5) → boards/<n>/design/{netlist, perfil}."""
    from pcbforge import brain as cb
    pedido = str(corpo.get("pedido") or "").strip()
    nome = str(corpo.get("nome") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9-]+", nome) or not nome:
        raise HTTPException(400, f"nome '{nome}' fora de [A-Za-z0-9-] (§13.8)")
    pasta, pasta_d = (ROOT / "boards", ), None
    pasta = pasta[0] / nome
    pasta_d = pasta / "design"
    if pasta_d.exists():
        raise HTTPException(409, f"projeto '{nome}' já existe")
    # F14e: REAPROVEITA a sugestão que o usuário aprovou na prévia (mesma
    # prévia mostrada = mesma netlist criada — fim do U00 fantasma).
    sug = _cache_sugestao.get(pedido)
    if sug is None:
        bruto, estados = cb.interpretar(pedido) if pedido else (None, ["pedido_vazio"])
        if bruto is None:
            raise HTTPException(502, "brain indisponível: " + "; ".join(estados))
        sug = cb.construir_sugestao(bruto)
        if len(_cache_sugestao) > 20:
            _cache_sugestao.pop(next(iter(_cache_sugestao)))
        _cache_sugestao[pedido] = sug
    bloqueios = _bloqueio_criacao(sug)
    if bloqueios:
        raise HTTPException(422, "sugestão com erro(s): " + "; ".join(bloqueios))
    pasta_d.mkdir(parents=True)
    doc = {"_comentario": "gerado pelo brain (§5) — REVISAR antes de gerar KiCad (§13.1)",
           "version": "1.0",
           "metadata": {"pedido": pedido[:400], "gerado_por": cb.MODELO,
                        "gerado_em": time.strftime("%Y-%m-%d %H:%M")},
           "components": sug["components"],
           "connections": sug["connections"],
           "rails": [{"net": r} for r in ("VCC", "GND")
                     if any(c.get("net_name") == r for c in sug["connections"])],
           # revisão §13.1: respostas do usuário + suposições editáveis ficam
           # gravadas no doc (F14e — o brain registra o que assumiu)
           "constraints": {"omitido": sug.get("omitido", []),
                           "decisoes_padrao": sug.get("decisoes_padrao", [])}}
    (pasta_d / "netlist.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    pf = sug["perfil"]
    (pasta_d / "board_profile.yaml").write_text(
        _yaml_do_perfil(nome, pedido, int(pf.get("camadas", 1)),
                        pf.get("size_mm", {})),
        encoding="utf-8")
    return {"criado": nome, "com_avisos": bool(sug["omitido"]), "omitido": sug["omitido"]}


@API.get("/api/projetos")
def projetos() -> list[dict]:
    from pcbforge.verify import checklist as vchk
    out = []
    boards = sorted((ROOT / "boards").iterdir()) if (ROOT / "boards").is_dir() else []
    for pasta in boards:
        if not pasta.is_dir():
            continue
        try:
            resultado = vchk.checklist_pre_fab(pasta)
            out.append({"nome": pasta.name, "pronto": resultado["pronto"],
                        "itens": resultado["itens"], "texto": resultado["texto"]})
        except Exception as e:  # §9: mostra problema, não derruba a lista
            out.append({"nome": pasta.name, "pronto": False, "erro": str(e)})
    return out


@API.get("/api/projetos/{nome}/netlist")
def netlist_get(nome: str) -> dict:
    pasta = _placa(nome)
    f = pasta / "design" / "netlist.json"
    if not f.is_file():
        raise HTTPException(404, "sem netlist.json")
    return json.loads(f.read_text(encoding="utf-8"))


@API.put("/api/projetos/{nome}/netlist")
def netlist_put(nome: str, dados: dict) -> dict:
    """Salva o netlist revisado e roda a validação viva (§13.1)."""
    from pcbforge.core.validator import validar_netlist
    pasta = _placa(nome)
    erros = validar_netlist(dados)
    if not erros:
        (pasta / "design" / "netlist.json").write_text(
            json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"salvo": not erros, "problemas": erros}


@API.get("/api/projetos/{nome}/perfil")
def perfil_get(nome: str) -> dict:
    pasta = _placa(nome)
    f = pasta / "design" / "board_profile.yaml"
    if not f.is_file():
        raise HTTPException(404, "sem board_profile.yaml")
    return {"yaml": f.read_text(encoding="utf-8")}


@API.put("/api/projetos/{nome}/perfil")
def perfil_put(nome: str, corpo: dict) -> dict:
    """Salva o perfil revisado e roda a validação viva (§13.2)."""
    import yaml
    from pcbforge.core.validator import aplicar_default_espessura, validar_perfil
    pasta = _placa(nome)
    texto = corpo.get("yaml", "")
    try:
        dados = yaml.safe_load(texto) or {}
    except Exception as e:
        return {"salvo": False, "problemas": [{"codigo": "YAML", "msg": str(e)}]}
    aplicar_default_espessura(dados)
    erros = validar_perfil(dados)
    if not erros:
        (pasta / "design" / "board_profile.yaml").write_text(texto, encoding="utf-8")
    return {"salvo": not erros, "problemas": erros}


def _lanca_e_monitora(nome: str, seed: int) -> None:
    """Thread do build: stdout no build.log; estado vira ok/falha ao terminar."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "pcbforge.cli", "build", nome, "--seed", str(seed)],
        cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    saida: list[str] = []
    for linha in proc.stdout or []:
        saida.append(linha.rstrip())
    proc.wait()
    with _lock:
        _estados_build[nome].update(
            estado="ok" if proc.returncode == 0 else "falha",
            retorno=proc.returncode,
            saida="\n".join(saida[-60:]),
            state_live=False)


@API.post("/api/projetos/{nome}/build")
def build_post(nome: str, seed: int = 5) -> dict:
    _placa(nome)
    _gate_pre_build(nome)   # §19.3 — nunca dispara build condenado
    with _lock:
        anterior = dict(_estados_build.get(nome) or {})
        if anterior.get("state_live"):
            raise HTTPException(409, "build já em andamento para este projeto")
        _estados_build[nome] = {"estado": "rodando", "inicio": time.time(), "state_live": True}
    threading.Thread(target=_lanca_e_monitora, args=(nome, seed), daemon=True).start()
    return {"iniciado": True, "seed": seed}


def _gate_pre_build(nome: str) -> None:
    """§19.3 — gera preflight ALL-verde: valida netlist + catálogo de footprints.
    Falha → 422 com o ref da peça causadora (nunca 'undefined')."""
    import yaml
    from pcbforge.core.validator import validar_netlist
    from pcbforge.parts import catalogo
    pasta = _placa(nome)
    try:
        nl = json.loads((pasta / "design" / "netlist.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise HTTPException(422, f"netlist ilegível: {e}")
    erros = [p for p in validar_netlist(nl) if p.get("severidade") == "erro"]
    if erros:
        raise HTTPException(422, "netlist inválida: "
                            + "; ".join(f"{p['codigo']}: {p['mensagem']}" for p in erros))
    ruins = [c["ref"] for c in nl.get("components", [])
             if not catalogo.apto(c.get("footprint_ref", ""))
             and not (c.get("type") == "montadora")]
    if ruins:
        raise HTTPException(422, "footprint(s) fora do catálogo apto (pads reais + 3D): "
                            + ", ".join(ruins))


@API.get("/api/projetos/{nome}/build/status")
def build_status(nome: str) -> dict:
    from pcbforge.verify import checklist as vchk
    pasta = _placa(nome)
    log = pasta / "build.log"
    linhas = log.read_text(encoding="utf-8", errors="replace").splitlines()[-40:] \
        if log.is_file() else []
    with _lock:
        build = dict(_estados_build.get(nome) or {})
    try:
        pronto = vchk.checklist_pre_fab(pasta)
    except Exception as e:  # §9
        pronto = {"pronto": False, "texto": f"checklist falhou: {e}"}
    return {"build": build, "log": linhas, "checklist": pronto}


@API.get("/api/projetos/{nome}/seeds")
def seeds(nome: str) -> dict:
    """Viabilidade do placement por seed (§4.3.2b — reorganização, sem inventar)."""
    import yaml
    from pcbforge.core import placement as pl
    from pcbforge.core.validator import aplicar_default_espessura
    pasta = _placa(nome)
    try:
        netlist = json.loads((pasta / "design" / "netlist.json").read_text(encoding="utf-8"))
        perfil = yaml.safe_load(
            (pasta / "design" / "board_profile.yaml").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise HTTPException(404, f"netlist/perfil ilegíveis: {e}")
    aplicar_default_espessura(perfil or {})
    if not netlist.get("components"):
        raise HTTPException(422, "netlist sem componentes — não há o que otimizar (§4.3.2b)")
    resultado = []
    for s in range(1, 9):
        layout, mm0, mm1 = pl.otimizar(netlist, perfil, seed=s, iteracoes=600)
        conges = pl.contar_conflitos(pl.coords_pads(netlist, layout)[1])
        cruzes = pl.contar_cruzamentos(netlist, layout)
        resultado.append({"seed": s, "mst_mm": round(mm1, 1), "sobreposicoes": conges,
                          "cruzamentos": cruzes,
                          "viavel_1l": conges == 0 and cruzes == 0})
    return {"seeds": resultado}


@API.get("/api/projetos/{nome}/renders")
def renders(nome: str) -> dict:
    pasta = _placa(nome)
    dir_r = pasta / "outputs" / "renders"
    return {"renders": sorted(f.name for f in dir_r.glob("*.png")) if dir_r.is_dir() else []}


@API.get("/api/projetos/{nome}/renders/{arquivo}")
def render_file(nome: str, arquivo: str) -> FileResponse:
    pasta = _placa(nome)
    if not re.fullmatch(r"[\w.-]+\.png", arquivo):
        raise HTTPException(400, "arquivo inválido")
    f = pasta / "outputs" / "renders" / arquivo
    if not f.is_file():
        raise HTTPException(404, "sem render")
    return FileResponse(f, media_type="image/png")


@API.get("/api/projetos/{nome}/zip")
def zip_download(nome: str) -> FileResponse:
    pasta = _placa(nome)
    zips = sorted((pasta / "outputs").glob("*-v1-1c-*.zip"))
    if not zips:
        raise HTTPException(404, "sem zip Gerbers — rode o build")
    return FileResponse(zips[-1], filename=zips[-1].name)


@API.get("/api/projetos/{nome}/bom-interativo")
def bom_interativo(nome: str) -> dict:
    """InteractiveHtmlBom CLI — prévia interativa quando disponível (F3/F5)."""
    pasta = _placa(nome)
    candidatos = [
        ROOT / "tools" / "InteractiveHtmlBom" / "InteractiveHtmlBom" / "generate_interactive_bom.py",
    ]
    _plug = paths.plugins_dir()
    if _plug:
        candidatos.append(_plug / "InteractiveHtmlBom" / "generate_interactive_bom.py")
    gerador = next((c for c in candidatos if c.is_file()), None)
    if not gerador:
        return {"disponivel": False}
    return {"disponivel": True, "gerador": str(gerador)}

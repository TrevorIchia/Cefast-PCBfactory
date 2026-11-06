#!/usr/bin/env python3
"""pcbforge CLI — interface única com o pipeline (Plano Mestre §11).

Comandos disponíveis na v1:
  doctor   — diagnóstico do ambiente (delegates para pcbforge/doctor.py)
  new      — cria a pasta de um projeto de placa com esqueleto completo
  (build/route/export/parts chegam nos marcos M2–M5.)

Uso: .venv/bin/python -m pcbforge.cli <comando>
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import click
import yaml  # noqa: F401  (usado por comandos futuros)

from pcbforge import paths

ROOT = paths.root()
KI_PY = ("/Applications/KiCad.app/Contents/Frameworks/Python.framework/"
         "Versions/3.9/bin/python3.9")
KICAD_CLI = "/Applications/KiCad.app/Contents/MacOS/kicad-cli"


@click.group()
@click.version_option("1.0.0-m3")
def cli() -> None:
    """PCBForge — de linguagem natural a placa fabricável."""


@cli.command("serve")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--porta", "--port", "porta", default=8000, show_default=True, type=int)
def serve(host: str, porta: int) -> None:
    """Painel web de fabricação (F3 — M9)."""
    import uvicorn
    from pcbforge.gui.app import API

    click.echo(f"PCBForge serve em http://{host}:{porta} (Ctrl+C para sair)")
    uvicorn.run(API, host=host, port=porta, log_level="warning")


@cli.command()
@click.argument("pedido")
@click.option("--criar", default=None, help="name do projeto novo — cria boards/<nome>/design/ com netlist+perfil")
def brain(pedido: str, criar: str | None) -> None:
    """Pedido em linguagem natural → netlist proposta (F4 — M10, §5/§13.3)."""
    from pcbforge import brain as cb

    click.echo(f"analisando com opencode ({cb.MODELO})…")
    bruto, estados = cb.interpretar(pedido)
    if bruto is None:
        raise click.ClickException("bruto indisponível: " + "; ".join(estados))
    sugestao = cb.construir_sugestao(bruto)
    click.echo(cb.propor_previa(sugestao))
    click.echo(f"\nvalidador: {len(sugestao['validador'])} problema(s)"
               + (" — revise no painel `pcbforge serve`" if sugestao["validador"] else ""))
    blocos = sugestao.get("bloqueios") or [p for p in sugestao["validador"]
                                           if p.get("severidade") == "erro"]
    if criar and not blocos:
        pasta = ROOT / "boards" / criar
        (pasta / "design").mkdir(parents=True, exist_ok=True)
        doc = {
            "_comentario": "gerado pelo brain (§5) — REVISAR antes de gerar KiCad (§13.1)",
            "version": "1.0",
            "metadata": {"pedido": pedido[:400],
                         "gerado_por_cb": cb.MODELO,
                         "gerado_em": time.strftime("%Y-%m-%d %H:%M")},
            "components": sugestao["components"],
            "connections": sugestao["connections"],
            "rails": [{"net": r} for r in ("VCC", "GND")
                      if any(c.get("net_name") == r for c in sugestao["connections"])],
            "constraints": {},
        }
        (pasta / "design" / "netlist.json").write_text(
            json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        click.echo(f"netlist proposta gravada em {pasta / 'design' / 'netlist.json'}")
        # F7: build precisa de board_profile.yaml — mesmos defaults do `new` (§4),
        # com size_mm/camadas vindos do brain (revisar antes de gerar — §13.1)
        p = sugestao["perfil"] or {}
        perfil = {
            "name": criar,
            "stackup": {
                "layers": int(p.get("camadas") or 1),
                "board_material": "FR4",
                "copper_oz": 1.0,
                "thickness_mm": 1.6,
                "color": "green",
                "silkscreen": "white",
            },
            "gold_fingers": False,
            "size_mm": p.get("size_mm") or {"w": 50, "h": 30},
            "outline_shape": "retângulo",
            "mounting": {"diameter_mm": 3.2, "corners": 4, "margin": 3},
            "min_trace_mm": 0.25,
            "min_clearance_mm": 0.25,
            "min_via_mm": 0.5,
            "high_current_traces": [],
            "autoroute": {"timeout_s": 600, "max_vias": None, "layers_allowed": None},
            "assembly_jlcpcb": False,
            "thermal_reliefs": True,
            "notes": f"gerado pelo brain ({cb.MODELO}) — REVISAR antes de gerar (§13.1)",
        }
        (pasta / "design" / "board_profile.yaml").write_text(
            yaml.dump(perfil, allow_unicode=True), encoding="utf-8")
        click.echo(f"perfil gravado em {pasta / 'design' / 'board_profile.yaml'}")


@cli.command()
def doctor() -> None:
    """Verifica o ambiente (tabela verde/amarelo/vermelho)."""
    import subprocess
    import sys

    ret = subprocess.run([sys.executable, str(ROOT / "pcbforge" / "doctor.py")])
    sys.exit(ret.returncode)


@cli.command("catalogo")
@click.option("--regenerar", is_flag=True, help="reescreve config/catalogo.json do censo de footprints")
def catalogo(regenerar: bool) -> None:
    """Censo dos footprints aptos (F1 — limpa de componentes)."""
    from pcbforge.parts import catalogo as cat

    if regenerar:
        meta = cat.gerar_catalogo()
        click.echo(f"catalogo.json regenerado: {meta['total']} aptos "
                   f"({meta['smd']} smd, {meta['tht']} tht) — {meta['data_censo']}")
    dados = cat.carregar()
    click.echo(f"catálogo ativo: {len(dados)} footprints aptos (config/catalogo.json)")


@cli.command()
@click.argument("nome")
def checklist(nome: str) -> None:
    """Checklist pré-fabricação (F2 — V-plane) para boards/<nome>/."""
    import re

    from pcbforge.verify import checklist as vchk

    if not re.fullmatch(r"[A-Za-z0-9-]+", nome):
        raise click.ClickException("nome só pode conter [A-Za-z0-9-] (regra do plano §13.8)")
    pasta = ROOT / "boards" / nome
    if not (pasta / "design").is_dir():
        raise click.ClickException(f"projeto '{nome}' não tem design/")
    resultado = vchk.checklist_pre_fab(pasta)
    click.echo(resultado["texto"])
    sys.exit(0 if resultado["pronto"] else 1)


@cli.command()
@click.argument("nome")
@click.option("--camadas", type=int, default=2, show_default=True, help="nº de camadas (1 = face simples)")
def new(nome: str, camadas: int) -> None:
    """Cria boards/<NOME>/ com o esqueleto completo (design/, kicad/, outputs/, verify/)."""
    if not all(c.isalnum() or c == "-" for c in nome):
        raise click.ClickException("nome só pode conter [A-Za-z0-9-] (regra do plano §13.8)")

    pasta = ROOT / "boards" / nome
    if pasta.exists():
        raise click.ClickException(f"projeto '{nome}' já existe em {pasta}")

    (pasta / "design").mkdir(parents=True)
    (pasta / "kicad").mkdir()
    (pasta / "outputs" / "renders").mkdir(parents=True)
    (pasta / "verify").mkdir()

    # request.md — o pedido original do usuário
    (pasta / "design" / "request.md").write_text(
        f"# Pedido — {nome}\n\n(descreva aqui o circuito em linguagem natural)\n",
        encoding="utf-8")

    # board_profile.yaml — defaults alinhados ao Plano Mestre §4
    perfil = {
        "name": nome,
        "stackup": {
            "layers": camadas,
            "board_material": "FR4",
            "copper_oz": 1.0,
            "thickness_mm": 1.6,
            "color": "green",
            "silkscreen": "white",
        },
        "gold_fingers": False,
        "size_mm": {"w": 60, "h": 40},
        "outline_shape": "retângulo",
        "mounting": {"diameter_mm": 3.2, "corners": 4, "margin": 3},
        "min_trace_mm": 0.25,
        "min_clearance_mm": 0.25,
        "min_via_mm": 0.5,
        "high_current_traces": [],
        "autoroute": {"timeout_s": 600, "max_vias": None, "layers_allowed": None},
        "assembly_jlcpcb": False,
        "thermal_reliefs": True,
        "notes": "criado pelo pcbforge CLI (M1)",
    }
    (pasta / "design" / "board_profile.yaml").write_text(yaml.dump(perfil, allow_unicode=True), encoding="utf-8")

    # netlist.json vazio (fonte de verdade; será preenchido pelo cérebro)
    (pasta / "design" / "netlist.json").write_text(
        '{\n  "version": "1.0",\n  "components": [],\n  "connections": [],\n  "rails": [],\n  "constraints": []\n}\n',
        encoding="utf-8")

    click.echo(f"✅ projeto '{nome}' criado ({pasta}) com perfil de {camadas} camada(s) — face "
               + ("simples" if camadas == 1 else "dupla" if camadas == 2 else f"múltipla ({camadas})"))


@cli.command()
@click.argument("nome")
@click.option("--sem-rotas", is_flag=True, help="gera KiCad esqueleto sem chamar Freerouting")
@click.option("--sem-otimizacao", is_flag=True, help="pula a otimização de placement (MST)")
@click.option("--seed", default=1, show_default=True, type=int,
              help="semente do otimizador — mude-a para 'reorganizar a placa' e re-rotear")
def build(nome: str, sem_rotas: bool, sem_otimizacao: bool, seed: int) -> None:
    """Pipeline completo do projeto <NOME> (M3–M6): validar → sch → pcb → rota → drc/erc → export."""
    import json as _json
    from datetime import datetime
    from pathlib import Path

    import yaml

    sistema_root = Path(__file__).resolve().parent.parent
    pasta = sistema_root / "boards" / nome
    design = pasta / "design"
    netlist_path = design / "netlist.json"
    perfil_path = design / "board_profile.yaml"
    if not netlist_path.exists():
        raise click.ClickException(f"projeto '{nome}' não tem design/netlist.json")

    netlist = _json.loads(netlist_path.read_text())
    perfil = yaml.safe_load(perfil_path.read_text()) if perfil_path.exists() else {}

    log: list[str] = []
    t0 = datetime.now()
    log.append(f"pcbforge build de '{nome}' iniciado {t0:%Y-%m-%d %H:%M:%S}")

    def _log_final(erro: str | None) -> None:
        """§13.5: build.log SEMPRE é escrito — inclusive em falha (parcial)."""
        fim = datetime.now()
        linhas = list(log)
        if erro:
            linhas.append(f"ERRO até aqui: {erro}")
        else:
            linhas.append(f"pcbforge build de '{nome}' termino OK {fim:%H:%M:%S} "
                          f"({(fim - t0).seconds}s)")
        (pasta / "build.log").write_text("\n".join(linhas) + "\n", encoding="utf-8")

    try:
        # 1. Validar (§13.7: coerência antes de gerar)
        from pcbforge.core.validator import aplicar_default_espessura, validar_netlist, validar_perfil
        problemas = validar_netlist(netlist) + validar_perfil(perfil)
        erros = [p for p in problemas if p["severidade"] == "erro"]
        if erros:
            for p in problemas:
                log.append(f"  [{'ERRO' if p['severidade']=='erro' else 'avis'}] {p['mensagem']}")
            raise click.ClickException(f"netlist/perfil inválidos ({len(erros)} erro(s)). Corrija o design/.")
        aplicar_default_espessura(perfil)
        log.append("netlist + perfil validados (U01–U08 verdes)")

        # 2. Gerar esquemático + PCB (com placement otimizado quando ativo)
        from pcbforge.generator.schematic import gerar_esquematico
        from pcbforge.generator.pcb import aplicar_regras_projeto, gerar_pcb
        pasta_kicad = pasta / "kicad"
        sch = gerar_esquematico(netlist, pasta_kicad, nome)

        layout = None
        if not sem_rotas and not sem_otimizacao:
            from pcbforge.core.placement import comprimento_estimado, contar_conflitos, coords_pads, otimizar
            tentativas = int((perfil.get("autoroute") or {}).get("tentativas", 3))
            n_it = int((perfil.get("autoroute") or {}).get("otimizacao_iteracoes", 600))
            for tent_p in range(tentativas):
                seed_t = seed + tent_p
                layout, mm0, mm1 = otimizar(netlist, perfil, seed=seed_t, iteracoes=n_it)
                # Regra dura (F0): sobreposição é violação — nada rota/deve rotar assim.
                # §4.3.2b: placement conflitante não aborta — gira seed (o conflito
                # pode ser local mínimo da seed, não do netlist)
                n_conf = contar_conflitos(coords_pads(netlist, layout)[1])
                if n_conf == 0:
                    log.append(f"placement otimizado (seed {seed_t}): trilhas ESTIMADAS "
                               f"{mm0:.0f}mm → {mm1:.0f}mm ({100*(mm0-mm1)/max(mm0, 1):.0f}% menor, "
                               "sem executar roteador)")
                    log.append("verificação dura: 0 sobreposições entre componentes")
                    break
                log.append(f"  placement seed {seed_t}: {n_conf} sobreposição(ões) "
                           "— próximo seed")
            else:
                raise click.ClickException(
                    f"layout com sobreposição(ões) em {tentativas} seed(s) — reorganize pos_mm "
                    "no netlist, aumente size_mm ou otimizacao_iteracoes em "
                    "design/board_profile.yaml e re-roteie")

        pcb = gerar_pcb(netlist, perfil, pasta_kicad, nome, layout=layout)
        aplicar_regras_projeto(pasta_kicad, nome, perfil)
        log.append("constraints do perfil aplicadas ao .kicad_pro "
                   f"(trace {perfil.get('min_trace_mm', 0.25)}mm, clearance "
                   f"{perfil.get('min_clearance_mm', 0.25)}mm)")
        log.append(f"esquemático + pcb gerados ({sch.stat().st_size}/{pcb.stat().st_size} bytes)")

        camadas = int(perfil["stackup"]["layers"])

        # 3. Roteamento (M4) + face simples (§4.3)
        if not sem_rotas and camadas >= 1:
            from pcbforge.routing import facesimples, run as rt
            from pcbforge.routing.outlines import reclassificar_outlines
            from pcbforge.routing.verifica_ses import verificar_ses
            dsn = pasta / "outputs" / f"{nome}.dsn"
            ses = pasta / "outputs" / f"{nome}.ses"
            dsn.parent.mkdir(parents=True, exist_ok=True)
            timeout = int((perfil.get("autoroute") or {}).get("timeout_s", 600))
            log.append("§13.4: neckdown automático DESLIGADO (largura mínima "
                       f"{perfil.get('min_trace_mm', 0.25)}mm respeitada) — "
                       "--router.automatic_neckdown=false (issues #978/#973)")
            tentativas = int((perfil.get("autoroute") or {}).get("tentativas", 3))
            from pcbforge.routing.run import rodar_drc, rodar_erc
            resumo = None
            erc = drc = None
            sucesso = False
            # §13.4/§4.3(2)(b): cada tentativa RE-ORGANIZA o placement (novo seed);
            # tentar de novo com DSN idêntico é inútil (determinismo provado na F0).
            # O DRC entra no loop: neckdown fantasma do fanout (track/connection_width
            # abaixo do mínimo mesmo com a flag off) é bloqueador e depende do
            # placement — o seed seguinte resolve (issues #973/#978, v2.5.0).
            variar_placement = layout is not None
            quebras_ultimo: dict | None = None
            novas_pontes: list[str] = []          # F14c pontes 0Ω feitas
            ponte_max = int((perfil.get("autoroute") or {}).get("ponte_max", 6))
            from pcbforge.core import ponte
            for tent in range(1, tentativas + 1):
                if tent > 1 and variar_placement:
                    seed_t = seed + tent - 1
                    layout_t, _, _ = otimizar(netlist, perfil, seed=seed_t, iteracoes=600)
                    n_conf_t = contar_conflitos(coords_pads(netlist, layout_t)[1])
                    if n_conf_t > 0:
                        log.append(f"  tentativa {tent}: seed {seed_t} descartado "
                                   f"({n_conf_t} sobreposição(ões)) — próximo seed")
                        continue
                    pcb = gerar_pcb(netlist, perfil, pasta_kicad, nome, layout=layout_t)
                    aplicar_regras_projeto(pasta_kicad, nome, perfil)
                    log.append(f"  tentativa {tent}: placement re-organizado (seed {seed_t})")
                rt.exportar_dsn(pcb, dsn, log)
                if camadas == 1:
                    mod, msg = facesimples.bloqueio_b_cu(dsn)
                    log.append(f"face simples: {'aplicado' if mod else 'sem mudança'} — {msg}")
                # outlines (courtyard/silk exportados como cobre pelo KiCad 10.0.7)
                # viram keepout fantasma no Freerouting 2.5.0 → nets incompletas +
                # "0 unrouted" falso (bug classe v2.2.4; provado 2026-10-28, I04).
                # Reclassificar signal→silk (run E): router ignora e o DSN segue
                # visível para inspeção — sem apagar nada.
                mod_o, msg_o = reclassificar_outlines(dsn)
                log.append(f"outlines: {msg_o}")
                # regras do ROUTEADOR (diretriz 28-10-2026): clearance de roteamento
                # maior que o mínimo de fabricação (entorno de pads/ilhas) + largura
                # por corrente (B2: NXP 1mm/A) em classes próprias no DSN
                from pcbforge.routing.rules import aplicar as aplicar_regras_roteador
                aplicar_regras_roteador(dsn, perfil, netlist, log)
                resumo = rt.rotear(dsn, ses, timeout, log, tentativa=tent)
                log.append(f"  tentativa {tent}: unrouted={resumo.get('unrouted')}")
                if resumo.get("unrouted", 1) > 0:
                    # F14c §4.3.1(a) — ponte 0Ω automática (perfil autoroute.
                    # ponte_0ohm): insere resistor 0Ω em série em cada conexão
                    # presa, regenera sch+pcb e re-roteia no próximo ciclo.
                    if ponte_max > len(novas_pontes) \
                            and (perfil.get("autoroute") or {}).get("ponte_0ohm"):
                        loc, _ = coords_pads(netlist, layout)
                        refs_n = ponte.inserir_pontes(
                            netlist, resumo.get("na_roteadas") or [], loc)
                        if refs_n:
                            novas_pontes.extend(refs_n)
                            # a ponte nova precisa existir no layout: pos_mm
                            # dela (seed do placement), senão KeyError p/ baixo
                            for c in netlist["components"]:
                                if c["ref"] in refs_n:
                                    layout[c["ref"]] = (*c["pos_mm"], 0)
                            ponte.sincronizar(nome, pasta, netlist)
                            sch = gerar_esquematico(netlist, pasta_kicad, nome)
                            pcb = gerar_pcb(netlist, perfil, pasta_kicad, nome,
                                            layout=layout)
                            aplicar_regras_projeto(pasta_kicad, nome, perfil)
                            log.append(f"  tentativa {tent}: PONTE 0Ω inserida "
                                       f"({', '.join(refs_n)}) — netlist "
                                       "sincronizada, re-roteando")
                            continue
                    continue
                # verificação dura do SES (§4.3.2b): conferir ANTES de aplicar —
                # o router pode jurar 0 unrouted com nets ilhadas
                quebradas = verificar_ses(pcb, ses, log)
                if quebradas:
                    quebras_ultimo = quebradas
                    log.append(f"  tentativa {tent}: SES com {len(quebradas)} net(s) "
                               "ilhada(s) apesar de 0 unrouted — próximo seed")
                    continue
                rt.importar_ses(pcb, ses, log)
                # regra B1 (quinas): chanfro 90°→2×45° pós-SES; agudo (<90°)
                # é bloqueador — nunca exportar placa com acid trap
                from pcbforge.routing.angulos import corrigir_angulos
                n_chanfros, agudos = corrigir_angulos(pcb)
                if agudos:
                    log.append(f"ângulos (B1): {n_chanfros} chanfrada(s); "
                               f"AGUDOS: {len(agudos)}")
                    raise click.ClickException(
                        "trilhas com ângulo AGUDO (<90°) — acid trap (B1):\n  "
                        + "\n  ".join(agudos[:8]))
                log.append(f"ângulos (B1): {n_chanfros} quina(s) reta(s) "
                           "chanfrada(s) p/ 2×45°; agudos: 0")
                erc = rodar_erc(sch, log)
                drc = rodar_drc(pcb, log)
                if drc["desconexoes"]:
                    raise click.ClickException("DRC com desconexões — placa não exportável (regra de ouro §9)")
                if not drc["bloqueadores"]:
                    sucesso = True
                    break
                tipos = sorted({v.get("type", "?") for v in drc["bloqueadores"]})
                # Eligibilidade de retry (mesmo precedente do neckdown-fantasma,
                # F0/I03): bloqueadores dependentes do PLACEMENT — o seed próximo
                # re-organiza (courtyard real depende da rotação do fp: a 0° o
                # court da antena do U1 invade vizinhos, a 90° limpa — provado
                # F14c 31-10 com 2 violações seed-12 ↔ 0 seed-17).
                if set(tipos) <= {"track_width", "connection_width",
                                  "courtyards_overlap", "pth_inside_courtyard",
                                  "npth_inside_courtyard"} and variar_placement:
                    log.append(f"  tentativa {tent}: neckdown fantasma do fanout "
                               f"({', '.join(tipos)}, issues #973/#978) — "
                               "próximo seed reorganiza placement")
                    continue
                break  # outros bloqueadores: seed não resolve — reporta
            if not sucesso and resumo is not None:
                if resumo.get("unrouted", 1) > 0:
                    presas = "\n  ".join(resumo.get("na_roteadas") or [])
                    raise click.ClickException(
                        f"Freerouting deixou {resumo.get('unrouted')} conexões não roteadas "
                        f"após {tentativas} tentativa(s) com placement(s) diferente(s).\n"
                        f"Conexões presas (pins exatos):\n  {presas}\n"
                        "Opções (§4.3.1 — nunca decido sozinho; pergunte ao usuário):\n"
                        "  (a) adicionar resistor 0Ω como ponte sobre o cruzamento\n"
                        "  (b) reorganizar posicionamento (pos_mm no netlist / outro seed)\n"
                        "  (c) mudar o perfil para 2 camadas (stackup.layers em board_profile.yaml)")
                if quebras_ultimo is not None:
                    det = "; ".join(f"{n}: {len(g)} grupo(s)" for n, g in quebras_ultimo.items())
                    raise click.ClickException(
                        f"Freerouting declarou 0 unrouted mas o SES ficou com nets ilhadas "
                        f"após {tentativas} tentativa(s) ({det}) — bug classe "
                        f"'premature routing-complete detection' (v2.2.4 fix; ver "
                        f"routing/outlines.py e outputs/*.frlog).\n"
                        "Opções (§4.3.1 — nunca decido sozinho; pergunte ao usuário):\n"
                        "  (a) reorganizar posicionamento (pos_mm no netlist / outro seed)\n"
                        "  (b) mudar o perfil para 2 camadas (stackup.layers em board_profile.yaml)")
                raise click.ClickException(
                    f"DRC com {len(drc['bloqueadores'])} violação(ões) bloqueadora(s) "
                    f"após {tentativas} tentativa(s) com placement(s) diferente(s) — "
                    "lista em verify/drc_report.json")
        else:
            erc = drc = None

        # 4. Verificação (M6): ERC + DRC (já rodou dentro do loop de roteamento?)
        from pcbforge.routing.run import rodar_drc, rodar_erc
        if drc is None:
            erc = rodar_erc(sch, log)
            drc = rodar_drc(pcb, log)
        if drc["desconexoes"]:
            raise click.ClickException("DRC com desconexões — placa não exportável (regra de ouro §9)")
        if drc["bloqueadores"]:
            raise click.ClickException("DRC com violações bloqueadoras — lista em verify/drc_report.json")

        # 5. Export (M5)
        from pcbforge.export import outputs as ex
        out = pasta / "outputs"
        ex.exportar_gerbers(pcb, out / "gerbers", camadas=camadas)
        ex.exportar_centroid(pcb, out / "centroid.csv")
        ex.exportar_step(pcb, out / "board.step")
        ex.exportar_renders(pcb, out / "renders")
        ex.exportar_pdf_sch(sch, out / f"{nome}-esquematico.pdf")
        ex.gerar_bom_csv(netlist, out / "bom.csv")
        from kiutils.footprint import Footprint  # só para manter import local leve
        zip_ = ex.zipar_gerbers(out / "gerbers", out, nome, versao=1, camadas=camadas)
        log.append(f"export concluído: {zip_.name}")

        # 6. build.log (§13.5)
        fim = datetime.now()
        log.append(f"pcbforge build de '{nome}' termino OK {fim:%H:%M:%S} "
                   f"({(fim - t0).seconds}s)")
        (pasta / "build.log").write_text("\n".join(log) + "\n", encoding="utf-8")
        click.echo("\n".join(log))
        # 6. build.log (§13.5) — sempre escrito (regra §13.5)
        _log_final(None)
        click.echo("\n".join(log))
        click.secho(f"\n✅ {nome}: placa fabricável em {pasta}", fg="green")
    except Exception as e:
        _log_final(str(e) or type(e).__name__)
        click.echo("\n".join(log))
        raise


if __name__ == "__main__":
    cli()

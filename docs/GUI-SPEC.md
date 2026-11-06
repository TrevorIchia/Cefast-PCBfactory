# GUI-SPEC — painel web (F3/M9, Plano Mestre §17 F3)

Um único `index.html` (vanilla JS, **sem node/npm**) atrás de FastAPI:
`python -m pcbforge.cli serve --host 127.0.0.1 --porta 8000`.

## Endpoints (`pcbforge/gui/app.py`)

| Método | Rota | O que faz |
|---|---|---|
| GET | `/` | página única (index.html) — abre no **cartão "Seu pedido (§5.1)"** |
| POST | `/api/brain` | pedido em linguagem natural → prévia revisável (F4/§5) |
| POST | `/api/brain/criar` | **Aprovação §5.1 passo 5** → cria `boards/<nome>/design/{netlist.json, board_profile.yaml}` de uma vez; `400` nome fora de §13.8; `409` se existe; `422` se validador ≠ 0; `502` se brain indisponível |
| GET | `/api/saude` | `{"ok": true}` |
| GET | `/api/projetos` | lista de projetos + **checklist vivo** por projeto |
| GET | `/api/projetos/{n}/netlist` | design/netlist.json |
| PUT | `/api/projetos/{n}/netlist` | **validação viva §13.1**: só salva se `validar_netlist` zerar |
| GET | `/api/projetos/{n}/perfil` | yaml do board_profile |
| PUT | `/api/projetos/{n}/perfil` | **validação viva §13.2** (+ defaults de espessura) |
| POST | `/api/projetos/{n}/build?seed=` | inicia build em thread (`409` se já roda); **gate pré-build §19.3**: valida netlist + catálogo e devolve `422` nomeando os refs problemáticos — nunca dispara build condenado |
| GET | `/api/projetos/{n}/build/status` | `{build: {estado, retorno, saida…}, log[], checklist}` |
| GET | `/api/projetos/{n}/seeds` | 8 seeds × MST/sobreposições/cruzamentos (§4.3.2b); `422` se netlist sem componentes |
| GET | `/api/projetos/{n}/renders` | nomes dos PNG |
| GET | `/api/projetos/{n}/renders/{arq}` | arquivo PNG |
| GET | `/api/projetos/{n}/zip` | **download** do zip Gerbers mais novo |
| GET | `/api/projetos/{n}/bom-interativo` | InteractiveHtmlBom — "quando disponível" (detecta plugin no KiCad/tools) |
| POST | `/api/brain` | motor IA (F4/M10): `{"pedido": …}` → prévia + sugestão + omitido |

## Comportamentos garantidos (§13)

- **§13.8 proteção de path**: nome precisa casar `[A-Za-z0-9-]+` — `..%2Fetc`
  → 400/404, nunca toca fora de `boards/`.
- **§13.1/13.2**: PUT com problema devolve `{salvo: false, problemas: […]}` e
  **não altera o arquivo em disco**.
- Build roda em **thread separada** invoando `python -m pcbforge.cli build
  <nome> --seed N`; estado termina `ok`/`falha` + `retorno`; o build.log do
  projeto é a fonte (§13.4) e a GUI refresca a cada **1,2 s** (polling).
- Erros **não derrubam a lista de projetos** (mostrados como `erro` no item).

## Fluxo da tela

1. barra esquerda: projetos com badge **pronto/incompleto** (do checklist);
2. abrir projeto: painéis de revisão (netlist JSON + perfil YAML) com botões
   "Validar e salvar";
3. faixa de build: ▶ Build (seed 5 default) + log ao vivo;
4. faixa direita: checklist item a item — ✅/❌ — link do zip + renders;
5. tabela de **seeds** para escolha informada antes de apertar build.

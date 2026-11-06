#!/usr/bin/env bash
# PCBForge — instalador universal Linux/macOS (F5 — M11, Plano Mestre §17).
#
# Idempotente: cada passo testa o artefato antes e pula o que já existe;
# instala só o faltante; termina com o `doctor` (0 🔴 = sucesso).
# Sem sudo: tudo que o projeto precisa fica na própria pasta (Rota B, §18);
# ferramentas globais (uv, OpenCode) instalam no $HOME do usuário.
#
# Uso:  ./install.sh [--somente-verificar]

set -euo pipefail

# instalações de usuário que nem todo shell (ex.: SSH não-login) carregam no PATH
export PATH="$HOME/.local/bin:$HOME/.opencode/bin:$PATH"

SOMENTE_VERIFICAR=false
case "${1:-}" in
  "") ;;
  --somente-verificar) SOMENTE_VERIFICAR=true ;;
  *) echo "uso: install.sh [--somente-verificar]"; exit 2 ;;
esac

# Código-fonte do motor (Opção A do repo Cefast-PCBfactory): quando o instalador
# roda por `curl|bash` (ou fora da pasta), ele baixa o tarball do repositório
# para ~/pcbforge (Plano §2.1) e continua — tudo o resto é idêntico.
REPO_URL="https://github.com/TrevorIchia/Cefast-PCBfactory"

if [[ ! -f "${BASH_SOURCE[0]}" || "${BASH_SOURCE[0]}" == "/dev/stdin" ]]; then
  ROOT="${PCBFORGE_HOME:-$HOME/pcbforge}"
else
  ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
cd "$ROOT" 2>/dev/null || { mkdir -p "$ROOT" && cd "$ROOT"; }
mkdir -p tools

ok()   { printf '  \033[32m✅\033[0m %s\n' "$*"; }
skip() { printf '  \033[36m⏭\033[0m  %s (já presente)\n' "$*"; }
info() { printf '  … %s\n' "$*"; }
fail() { printf '  \033[31m⛔ %s\033[0m\n' "$*"; }
# baixa(): 0 = prosseguir com o download (modo instalação); em
# --somente-verificar apenas reporta a falta e devolve 1 (pula o passo).
baixa() {
  if $SOMENTE_VERIFICAR; then fail "FALTA (só-verificar): $*"; return 1; fi
  info "baixando $*…"
}

[[ -f "$ROOT/pcbforge/cli.py" ]] && ok "repositório em $ROOT"
if [[ ! -f "$ROOT/pcbforge/cli.py" ]]; then
  if $SOMENTE_VERIFICAR; then
    fail "FALTA (só-verificar): código do motor não está em $ROOT"; exit 1
  fi
  info "código do motor ausente — baixando o repositório (tarball)…"
  tarball="$ROOT/cefast-main.tar.gz"
  curl -fsSL "$REPO_URL/archive/refs/heads/main.tar.gz" -o "$tarball" \
    || { fail "baixa do repo falhou — ver internet/URL $REPO_URL"; exit 1; }
  tar -xzf "$tarball" -C "$ROOT" --strip-components 1 \
    || { fail "extração falhou"; exit 1; }
  rm -f "$tarball"
  [[ -f "$ROOT/pcbforge/cli.py" ]] \
    || { fail "código não chegou direitinho — clonar manual: git clone $REPO_URL"; exit 1; }
  ok "repositório baixado para $ROOT"
fi

SO="$(uname -s)"; ARCH="$(uname -m)"
echo "== PCBForge instalador — $SO/$ARCH =="

# ————— 1. uv (gestor de Python, sem sudo — §2.2 passo 2, Rota B) —————
if command -v uv >/dev/null 2>&1; then
  skip "uv $(uv --version | cut -d' ' -f2)"
elif baixa "uv"; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

# ————— 2. Python 3.12 + venv do projeto (§2.2 passo 2) —————
VEN="$ROOT/.venv"
PYEXE=""
for cand in "$VEN/bin/python" "$VEN/Scripts/python.exe"; do
  if [[ -x "$cand" && "$("$cand" -c 'import sys; print(sys.version_info >= (3, 12))' 2>/dev/null || true)" == "True" ]]; then
    PYEXE="$cand"; break
  fi
done
if [[ -n "$PYEXE" ]]; then
  skip "venv $("$PYEXE" --version)"
elif baixa "venv Python 3.12 (uv)"; then
  command -v uv >/dev/null 2>&1 || { fail "uv ausente — passo 1 falhou"; exit 1; }
  uv venv .venv --python 3.12
  for cand in "$VEN/bin/python" "$VEN/Scripts/python.exe"; do
    [[ -x "$cand" ]] && PYEXE="$cand" && break
  done
fi

# ————— 3. Dependências do venv (requirements.txt com pins — F5) —————
DEPS="kiutils, click, yaml, fastapi, uvicorn, easyeda2kicad"
if [[ -x "$PYEXE" ]]; then
  if "$PYEXE" -c "import $DEPS" 2>/dev/null; then
    skip "deps do venv"
  elif [[ -f "$ROOT/requirements.txt" ]] && command -v uv >/dev/null 2>&1; then
    if baixa "dependências (requirements.txt)"; then
      "$PYEXE" -m ensurepip --quiet 2>/dev/null || true
      VIRTUAL_ENV="$VEN" uv pip install --python "$PYEXE" -r requirements.txt
    fi
  else
    fail "deps ausentes e uv/PYEXE insuficiente — rode manualmente:"; \
    echo "       VIRTUAL_ENV=$VEN uv pip install --python '$PYEXE' -r requirements.txt"
  fi
fi

# ————— 4. OpenCode CLI (motor IA §5; docs V2: opencode.ai/v2/docs) —————
if command -v opencode >/dev/null 2>&1; then
  skip "opencode $(opencode --version 2>/dev/null | head -1)"
elif baixa "OpenCode CLI (V2)"; then
  curl -fsSL https://opencode.ai/v2/install | bash
  export PATH="$HOME/.opencode/bin:$PATH"
fi

# ————— 5. Java ≥ 25 (Freerouting 2.5 exige classe 69 = Java 25) —————
export JAVA_HOME=""
if command -v java >/dev/null 2>&1 && java -version 2>&1 | grep -qE '"2[5-9]\.'; then
  skip "java no PATH ($(java -version 2>&1 | head -1))"
else
  ZH="$(find "$ROOT/tools" -maxdepth 6 -type f -name java -path '*bin/java' 2>/dev/null | head -1 || true)"
  if [[ -x "$ZH" ]]; then
    export JAVA_HOME="$(dirname "$(dirname "$ZH")")"        # <home>/bin/java → <home>
    export PATH="$JAVA_HOME/bin:$PATH"
    skip "java local ($(java -version 2>&1 | head -1))"
  elif baixa "Java (Zulu 25, JRE)"; then
    case "$SO" in
      Darwin) AZ_OS="macos" ;;
      Linux)  AZ_OS="linux" ;;
      *)      AZ_OS="" ;;
    esac
    AZ_ARCH="x64"
    case "$ARCH" in aarch64|arm64) AZ_ARCH="aarch64" ;; esac
    if [[ -n "$AZ_OS" ]]; then
      URL="$(curl -s "https://api.azul.com/metadata/v1/zulu/packages/?java_version=25&os=${AZ_OS}&arch=${AZ_ARCH}&archive_kind=targz&page=1&page_size=1" \
            | "$PYEXE" -c 'import json,sys; d=json.load(sys.stdin); print(d[0]["download_url"] if d else "")')"
      if [[ -n "$URL" ]]; then
        curl -L -o "$ROOT/tools/zulu25.tar.gz" "$URL"
        tar -xzf "$ROOT/tools/zulu25.tar.gz" -C "$ROOT/tools"
        rm -f "$ROOT/tools/zulu25.tar.gz"
        ZH="$(find "$ROOT/tools" -maxdepth 6 -type f -name java -path '*bin/java' | head -1)"
        export JAVA_HOME="$(dirname "$(dirname "$ZH")")"
        export PATH="$JAVA_HOME/bin:$PATH"
        ok "Java em $JAVA_HOME"
      else
        fail "baixa automática do Zulu falhou — coloque zulu25* em tools/ (§2.2)"
      fi
    else
      fail "SO '$SO' sem rotina de Java — instale Zulu 25 manualmente em tools/"
    fi
  fi
fi

# ————— 6. KiCad + bibliotecas embutidas (~4,8 GB — §2.2 passo 4) —————
KICAD_SHARED="$("$PYEXE" -c 'from pcbforge import paths; print(paths.kicad_shared() or "")' 2>/dev/null || true)"
if [[ -n "$KICAD_SHARED" ]]; then
  skip "KiCad ($KICAD_SHARED)"
elif $SOMENTE_VERIFICAR; then
  fail "FALTA: KiCad (símbolos/footprints/3D ~4,8 GB)"
elif [[ "$SO" == "Darwin" ]]; then
  info "baixando KiCad dmg (~4,8 GB, DEMORA)…"
  ASSETS="$(curl -s https://api.github.com/repos/KiCad/kicad-mac-builds/releases/latest \
           | "$PYEXE" -c '
import json, sys
try:
    rel = json.load(sys.stdin)
except Exception:
    sys.exit(0)
dmgs = [a["browser_download_url"] for a in rel.get("assets", []) if a.get("name", "").endswith(".dmg")]
intel = [u for u in dmgs if "Intel" in u]; arq = [u for u in dmgs if "arm64" in u or "Apple" in u]
pref = [u for u in dmgs if u not in intel and u not in arq]
print((intel or pref or dmgs or [""])[0])')"
  if [[ -n "$ASSETS" ]]; then
    curl -L -o "$ROOT/tools/kicad.dmg" "$ASSETS"
    hdiutil attach -nobrowse -quiet "$ROOT/tools/kicad.dmg"
    cp -R /Volumes/KiCad*/KiCad.app /Applications/ || true
    hdiutil detach -quiet /Volumes/KiCad* || true
    [[ -d /Applications/KiCad.app ]] && ok "KiCad instalado em /Applications" \
      || fail "app não copiado — abra o dmg manualmente em tools/kicad.dmg"
  else
    fail "baixa manual: https://www.kicad.org/download/ (dmg Intel)"
  fi
else
  fail "instale KiCad pelo gerenciador da distro (~4,8 GB, com bibliotecas):"
  echo "        Debian/Ubuntu: sudo add-apt-repository ppa:kicad/kicad-10.0-releases && sudo apt install kicad"
  echo "        Fedora:        sudo dnf install kicad"
fi

# ————— 7. Freerouting jar (roteador — §2.2 passo 5) —————
FR="$ROOT/tools/freerouting.jar"
if [[ -s "$FR" ]]; then
  skip "freerouting.jar ($(du -h "$FR" | cut -f1))"
elif baixa "freerouting.jar"; then
  curl -L -o "$FR" \
    "https://github.com/freerouting/freerouting/releases/latest/download/freerouting.jar" \
    && ok "freerouting.jar baixado" || fail "baixa manual: github.com/freerouting/freerouting/releases"
fi

# ————— 8. catalogo.json — censo dos footprints aptos (F1/M2) —————
if [[ -s "$ROOT/pcbforge/config/catalogo.json" ]]; then
  N="$("$PYEXE" -c 'from pcbforge.parts import catalogo; print(len(catalogo.carregar()))' \
       2>/dev/null | tail -1 || echo "?")"
  skip "catalogo.json (${N} footprints aptos)"
elif $SOMENTE_VERIFICAR; then
  fail "FALTA: pcbforge/config/catalogo.json (censo F1)"
elif [[ -x "$PYEXE" ]]; then
  info "gerando catalogo.json (censo, ~1 min)…"
  "$PYEXE" scripts/censo_footprints.py --regenerar || fail "censo do catálogo falhou"
else
  fail "FALTA catalogo.json e PYEXE indisponível — crie o venv (passo 2) e rode:"; \
  echo "       $PYEXE scripts/censo_footprints.py --regenerar"
fi

# ————— 9. Doctor final (0 🔴 = instalador verde) —————
echo
echo "== verificação final: doctor (0 🔴 = sucesso) =="
if [[ -x "$PYEXE" ]]; then
  export PCBFORGE_ROOT="$ROOT"
  "$PYEXE" pcbforge/doctor.py || fail "doctor reprovou — veja itens 🔴 acima"
else
  fail "doctor indisponível (Python/venv ausente — veja passos acima)"
fi

echo
echo "════════ PCBForge pronto (0 🔴) ════════"
echo "Cérebro: GLM 5.3 Flash grátis via OpenCode CLI (nada p/ configurar a mais)."
echo "Como usar:"
echo "  cd $ROOT && source scripts/env.sh"
echo "  1) $PYEXE -m pcbforge.cli doctor                  # ambiente ok?"
echo "  2) $PYEXE -m pcbforge.cli brain \"placa blink: led + resistor + conector 5V\""
echo "     → prévia da netlist pra revisar (regra §13.3: nunca inventa componente)"
echo "  3) $PYEXE -m pcbforge.cli serve                   # painel web do pedido"
echo "     http://127.0.0.1:8000   (revisar → aprovar → build → baixar zip)"
echo "  4) zip de Gerbers/JLCPCB em boards/<nome>/outputs/"
echo "Receita completa (passo a passo): docs/WORKFLOW-QUOTE.md"
exit 0

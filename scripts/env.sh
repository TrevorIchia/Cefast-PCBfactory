#!/bin/zsh
# scripts/env.sh — ambiente do PCBForge para a sessão do shell
# Uso: source /Users/user/pcbforge/scripts/env.sh

export PCBFORGE_ROOT="/Users/user/pcbforge"
export PCBFORGE_VENV="$PCBFORGE_ROOT/.venv"

# JAVA_HOME = Home de qualquer zulu em tools/ (layout mac/linux/extraído)
zulus=( "$PCBFORGE_ROOT"/tools/zulu*(N) )
export JAVA_HOME=""
if [[ -n "$zulus" ]]; then
  jbin="$(find "$zulus[1]" -maxdepth 5 -type f -name java -path '*bin/java' 2>/dev/null | head -1)"
  [[ -n "$jbin" ]] && export JAVA_HOME="$(dirname "$(dirname "$jbin")")"
fi

export PATH="$PCBFORGE_VENV/bin:$JAVA_HOME/bin:$HOME/.local/bin:$HOME/.opencode/bin:$PATH"

alias pcbforge-doctor="$PCBFORGE_VENV/bin/python $PCBFORGE_ROOT/pcbforge/doctor.py"
alias pcbforge-serve="$PCBFORGE_VENV/bin/python -m pcbforge.cli serve --porta 8777"

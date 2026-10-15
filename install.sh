#!/usr/bin/env bash
# Installs the second-brain skill for Claude Code (and optionally Codex).
# Usage: bash install.sh [--codex]
# --codex also installs to ~/.agents/skills (Codex user skills folder).
# Personal settings live in ~/.second-brain/ (config.json, local.md) and are never touched.
set -euo pipefail

src="$(cd "$(dirname "$0")" && pwd)/skills/second-brain"
targets=("$HOME/.claude/skills/second-brain")
if [[ "${1:-}" == "--codex" ]]; then targets+=("$HOME/.agents/skills/second-brain"); fi

for dst in "${targets[@]}"; do
  mkdir -p "$dst"
  (cd "$src" && find . -type f ! -name local.md ! -name config.json ! -path '*__pycache__*' -print0) |
    while IFS= read -r -d '' f; do
      mkdir -p "$dst/$(dirname "$f")"
      cp "$src/$f" "$dst/$f"
    done
  echo "Installed: $dst"
done
py=python3; python3 -c "" 2>/dev/null || py=python   # Windows Git Bash: python3 may be a Store alias
echo "Next: $py \"${targets[0]}/scripts/sb.py\" init <new vault folder>   (or: setup <existing vault>)"

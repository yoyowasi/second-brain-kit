#!/usr/bin/env bash
# Installs the second-brain skill for Claude Code (and optionally Codex),
# plus the Claude Code extras: hooks (session journal, dream, lint reminder) and the /inbox, /init-project skills.
# Usage: bash install.sh [--codex]
# --codex also installs the second-brain skill to ~/.agents/skills (Codex user skills folder).
# Personal settings live in ~/.second-brain/ (config.json, local.md) and are never touched.
# ~/.claude/settings.json and ~/.claude/CLAUDE.md are edited only when needed, after a .bak-<timestamp> copy.
set -euo pipefail

kit="$(cd "$(dirname "$0")" && pwd)"
src="$kit/skills/second-brain"
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

# Claude Code extras (hooks, /inbox, /init-project, settings.json hook entries, CLAUDE.md brain block)
py=python3; python3 -c "" 2>/dev/null || py=python   # Windows Git Bash: python3 may be a Store alias
"$py" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' ||
  { echo "Python 3.9+ not found as $py. Install it and run again." >&2; exit 1; }
"$py" "$kit/tools/claude_setup.py" install --python "$py" --claude-dir "$HOME/.claude"

echo "Next: $py \"${targets[0]}/scripts/sb.py\" init <new vault folder>   (or: setup <existing vault>)"
echo "Hooks summarize sessions with the claude CLI: run 'claude auth login' once in a terminal."

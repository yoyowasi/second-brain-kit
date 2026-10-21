#!/usr/bin/env bash
# Installs the second-brain skill for Claude Code (and optionally Codex and/or Antigravity),
# plus the Claude Code extras: hooks (session journal, dream, lint reminder) and the /inbox, /init-project skills.
# Usage: bash install.sh [--codex] [--antigravity] [--all]
# --codex also installs the second-brain skill to ~/.agents/skills (Codex user skills folder).
# --antigravity also installs it to ~/.gemini/config/skills (Antigravity user skills folder).
# --all is --codex --antigravity. Only the second-brain skill goes there; hooks and the other skills are Claude Code only.
# Personal settings live in ~/.second-brain/ (config.json, local.md) and are never touched.
# ~/.claude/settings.json and ~/.claude/CLAUDE.md are edited only when needed, after a .bak-<timestamp> copy.
set -euo pipefail

kit="$(cd "$(dirname "$0")" && pwd)"
for arg in "$@"; do
  case "$arg" in
    --codex|--antigravity|--all) ;;
    *) echo "Unknown option: $arg (use --codex, --antigravity, --all)" >&2; exit 1 ;;
  esac
done

py=python3; python3 -c "" 2>/dev/null || py=python   # Windows Git Bash: python3 may be a Store alias
"$py" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' ||
  { echo "Python 3.9+ not found as $py. Install it and run again." >&2; exit 1; }

# Skill copies (second-brain to every target; Claude Code extras: hooks, /inbox, /init-project, settings.json hook entries, CLAUDE.md brain block)
"$py" "$kit/tools/claude_setup.py" install --python "$py" --claude-dir "$HOME/.claude" --home "$HOME" "$@"

echo "Next: $py \"$HOME/.claude/skills/second-brain/scripts/sb.py\" init <new vault folder>   (or: setup <existing vault>)"
echo "Hooks summarize sessions with the claude CLI: run 'claude auth login' once in a terminal."

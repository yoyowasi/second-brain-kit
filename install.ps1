# Installs the second-brain skill for Claude Code (and optionally Codex and/or Antigravity),
# plus the Claude Code extras: hooks (session journal, dream, lint reminder) and the /inbox, /init-project skills.
# Usage: powershell -ExecutionPolicy Bypass -File install.ps1 [-Codex] [-Antigravity] [-All]
# -Codex also installs the second-brain skill to ~/.agents/skills (Codex user skills folder).
# -Antigravity also installs it to ~/.gemini/config/skills (Antigravity user skills folder).
# -All is -Codex -Antigravity. Only the second-brain skill goes there; hooks and the other skills are Claude Code only.
# Personal settings live in ~/.second-brain/ (config.json, local.md) and are never touched.
# ~/.claude/settings.json and ~/.claude/CLAUDE.md are edited only when needed, after a .bak-<timestamp> copy.
param([switch]$Codex, [switch]$Antigravity, [switch]$All)
$ErrorActionPreference = 'Stop'

if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw 'python not found on PATH. Install Python 3.9+ and run again.' }
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)"
if ($LASTEXITCODE -ne 0) { throw '"python" is not Python 3.9+ (or is the Microsoft Store alias). Install Python 3.9+ and run again.' }

# Skill copies (second-brain to every target; Claude Code extras: hooks, /inbox, /init-project, settings.json hook entries, CLAUDE.md brain block)
$flags = @()
if ($Codex -or $All) { $flags += '--codex' }
if ($Antigravity -or $All) { $flags += '--antigravity' }
python (Join-Path $PSScriptRoot 'tools\claude_setup.py') install --python python --claude-dir (Join-Path $HOME '.claude') --home $HOME @flags
if ($LASTEXITCODE -ne 0) { throw "tools\claude_setup.py failed (exit $LASTEXITCODE)" }

$sb = Join-Path $HOME '.claude\skills\second-brain\scripts\sb.py'
Write-Host "Next: python `"$sb`" init <new vault folder>   (or: setup <existing vault>)"
Write-Host "Hooks summarize sessions with the claude CLI: run 'claude auth login' once in a terminal."

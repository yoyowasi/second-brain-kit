# Installs the second-brain skill for Claude Code (and optionally Codex),
# plus the Claude Code extras: hooks (session journal, dream, lint reminder) and the /inbox, /init-project skills.
# Usage: powershell -ExecutionPolicy Bypass -File install.ps1 [-Codex]
# -Codex also installs the second-brain skill to ~/.agents/skills (Codex user skills folder).
# Personal settings live in ~/.second-brain/ (config.json, local.md) and are never touched.
# ~/.claude/settings.json and ~/.claude/CLAUDE.md are edited only when needed, after a .bak-<timestamp> copy.
param([switch]$Codex)
$ErrorActionPreference = 'Stop'

$src = Join-Path $PSScriptRoot 'skills\second-brain'
$targets = @(Join-Path $HOME '.claude\skills\second-brain')
if ($Codex) { $targets += Join-Path $HOME '.agents\skills\second-brain' }

foreach ($dst in $targets) {
    New-Item -ItemType Directory -Force -Path $dst | Out-Null
    Get-ChildItem -Path $src -Recurse -File |
        Where-Object { $_.Name -notin @('local.md', 'config.json') -and $_.FullName -notmatch '__pycache__' } |
        ForEach-Object {
            $out = Join-Path $dst $_.FullName.Substring($src.Length + 1)
            New-Item -ItemType Directory -Force -Path (Split-Path $out) | Out-Null
            Copy-Item -Path $_.FullName -Destination $out -Force
        }
    Write-Host "Installed: $dst"
}

# Claude Code extras (hooks, /inbox, /init-project, settings.json hook entries, CLAUDE.md brain block)
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw 'python not found on PATH. Install Python 3.9+ and run again.' }
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)"
if ($LASTEXITCODE -ne 0) { throw '"python" is not Python 3.9+ (or is the Microsoft Store alias). Install Python 3.9+ and run again.' }
python (Join-Path $PSScriptRoot 'tools\claude_setup.py') install --python python --claude-dir (Join-Path $HOME '.claude')
if ($LASTEXITCODE -ne 0) { throw "tools\claude_setup.py failed (exit $LASTEXITCODE)" }

$sb = Join-Path $targets[0] 'scripts\sb.py'
Write-Host "Next: python `"$sb`" init <new vault folder>   (or: setup <existing vault>)"
Write-Host "Hooks summarize sessions with the claude CLI: run 'claude auth login' once in a terminal."

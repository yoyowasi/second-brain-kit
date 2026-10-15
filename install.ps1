# Installs the second-brain skill for Claude Code (and optionally Codex).
# Usage: powershell -ExecutionPolicy Bypass -File install.ps1 [-Codex]
# -Codex also installs to ~/.agents/skills (Codex user skills folder).
# Personal settings live in ~/.second-brain/ (config.json, local.md) and are never touched.
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
$sb = Join-Path $targets[0] 'scripts\sb.py'
Write-Host "Next: python `"$sb`" init <new vault folder>   (or: setup <existing vault>)"

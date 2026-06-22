<#
  simulate-install.ps1 — run the REAL Windows installer in a throwaway sandbox.

  It invokes the actual install.ps1, but redirects uv's tool/bin/cache dirs and
  the clone into a temp sandbox and sets CONDUCTOR_NO_PATH=1, so NOTHING touches
  your real ~/.conductor, uv tools, or PATH. The sandbox is deleted at the end
  (keep it with -KeepSandbox). This is how you preview the install before doing
  it for real.

    powershell -ExecutionPolicy Bypass -File tools/simulate-install.ps1
    ... -Extras rag,honcho        # simulate the full install (heavier)
    ... -Init                     # also run `cdt init` to show scaffolding
    ... -Ref main -KeepSandbox    # pick a branch/tag, keep the sandbox

  Requires uv already installed (so the sim never bootstraps uv into your real
  ~/.local/bin). The real installer would install uv for a first-time user.
#>
[CmdletBinding()]
param(
  [string]$Ref    = 'feat/installer',
  [string]$Extras = 'none',   # 'none' = core-only (fast); 'rag,honcho' = full
  [switch]$Init,
  [switch]$KeepSandbox
)
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.UTF8Encoding]::new() } catch {}

$here      = Split-Path -Parent $MyInvocation.MyCommand.Path
$installer = Join-Path (Split-Path -Parent $here) 'install.ps1'
if (-not (Test-Path $installer)) { throw "install.ps1 not found at $installer" }
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  throw "uv not found. Install uv first — the sandbox must not bootstrap it into your real ~/.local/bin."
}

$sandbox = Join-Path $env:TEMP ("cdt-sim-" + [Guid]::NewGuid().ToString('N').Substring(0,8))
New-Item -ItemType Directory -Force -Path $sandbox | Out-Null
Write-Host ''
Write-Host "Sandbox: $sandbox" -ForegroundColor DarkGray

$keys  = 'UV_TOOL_DIR','UV_TOOL_BIN_DIR','UV_CACHE_DIR','CONDUCTOR_SRC','CONDUCTOR_REF','CONDUCTOR_EXTRAS','CONDUCTOR_NO_PATH'
$saved = @{}; foreach ($k in $keys) { $saved[$k] = [Environment]::GetEnvironmentVariable($k,'Process') }

try {
  $bin = Join-Path $sandbox 'bin'
  $env:UV_TOOL_DIR      = Join-Path $sandbox 'uv-tools'
  $env:UV_TOOL_BIN_DIR  = $bin
  $env:UV_CACHE_DIR     = Join-Path $sandbox 'uv-cache'
  $env:CONDUCTOR_SRC    = Join-Path $sandbox 'src'
  $env:CONDUCTOR_REF    = $Ref
  $env:CONDUCTOR_EXTRAS = $Extras
  $env:CONDUCTOR_NO_PATH = '1'

  Write-Host "Running the real install.ps1 (isolated; ref=$Ref; extras='$Extras')..." -ForegroundColor DarkGray
  Write-Host ('─' * 50) -ForegroundColor DarkGray
  & $installer
  Write-Host ('─' * 50) -ForegroundColor DarkGray

  Write-Host ''
  Write-Host '── Simulator verification ──' -ForegroundColor Cyan
  $cdt = Join-Path $bin 'cdt.exe'
  if (-not (Test-Path $cdt)) { throw "cdt.exe not found in the sandbox ($bin) — install did not complete" }
  Write-Host "✓ cdt.exe installed in sandbox" -ForegroundColor Green
  & $cdt --help | Select-Object -First 3 | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
  Write-Host "✓ cdt --help works" -ForegroundColor Green

  if ($Init) {
    $proj = Join-Path $sandbox 'proj'
    New-Item -ItemType Directory -Force -Path $proj | Out-Null
    Push-Location $proj
    try {
      git init -q
      '{}' | Out-File -Encoding utf8 package.json
      Write-Host ''
      Write-Host '── cdt init --target all ──' -ForegroundColor Cyan
      & $cdt init --target all --type fullstack
      $made = Get-ChildItem -Force -Directory | Where-Object { $_.Name -in '.claude','.opencode','.agents','.pi' } | Select-Object -Expand Name
      Write-Host ("✓ scaffolded: " + ($made -join ', ')) -ForegroundColor Green
    } finally { Pop-Location }
  }

  Write-Host ''
  Write-Host '✓ SIMULATION OK — the real install would behave exactly like this.' -ForegroundColor Green
  Write-Host '  Nothing was added to your PATH or ~/.conductor.' -ForegroundColor DarkGray
}
finally {
  foreach ($k in $keys) {
    if ($null -eq $saved[$k]) { Remove-Item "Env:\$k" -ErrorAction SilentlyContinue }
    else { Set-Item "Env:\$k" $saved[$k] }
  }
  if ($KeepSandbox) { Write-Host "Sandbox kept: $sandbox" -ForegroundColor Yellow }
  else { Remove-Item -Recurse -Force $sandbox -ErrorAction SilentlyContinue; Write-Host 'Sandbox cleaned.' -ForegroundColor DarkGray }
}

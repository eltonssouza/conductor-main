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
    ... -Library -Stacks java,angular   # demo corpus selection: download only those stacks
    ... -Ref main -KeepSandbox    # pick a branch/tag, keep the sandbox

  Requires uv already installed (so the sim never bootstraps uv into your real
  ~/.local/bin). The real installer would install uv for a first-time user.
#>
[CmdletBinding()]
param(
  [string]$Ref         = 'feat/installer',
  [string]$Extras      = 'none',   # 'none' = core-only (fast); 'rag,honcho' = full
  [switch]$Init,
  [switch]$Library,                # also demo the corpus stack-selection (download)
  [string]$Stacks      = 'java,angular',   # which stacks the demo "chooses"
  [string]$LibraryRef  = 'feat/stack-selection',  # library branch with the stack: tags
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

$keys  = 'UV_TOOL_DIR','UV_TOOL_BIN_DIR','UV_CACHE_DIR','CONDUCTOR_SRC','CONDUCTOR_REF','CONDUCTOR_EXTRAS','CONDUCTOR_NO_PATH',
         'PYTHONPATH','CONDUCTOR_LIBRARY','CONDUCTOR_LIBRARY_REF','CONDUCTOR_LIBRARY_TIERS','CONDUCTOR_LIBRARY_STACKS'
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

  if ($Library) {
    Write-Host ''
    Write-Host '── Library selection — download only the chosen stacks ──' -ForegroundColor Cyan

    # auto-detection preview: a Java + Angular sample project -> cdt detect
    $sample = Join-Path $sandbox 'sample'
    New-Item -ItemType Directory -Force -Path $sample | Out-Null
    '<project/>' | Out-File -Encoding utf8 (Join-Path $sample 'pom.xml')
    '{"dependencies":{"@angular/core":"^21.0.0","typescript":"5.6.0"}}' |
      Out-File -Encoding utf8 (Join-Path $sample 'package.json')
    Write-Host '  cdt detect (auto-pick from a Java+Angular project):' -ForegroundColor DarkGray
    & $cdt detect $sample | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }

    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
      Warn 'python not on PATH — skipping the download demo'
    } else {
      $libdir = Join-Path $sandbox 'library'
      $env:PYTHONPATH             = $env:CONDUCTOR_SRC
      $env:CONDUCTOR_LIBRARY      = $libdir
      $env:CONDUCTOR_LIBRARY_REF  = $LibraryRef
      $env:CONDUCTOR_LIBRARY_TIERS  = 'core'
      $env:CONDUCTOR_LIBRARY_STACKS = $Stacks
      Write-Host ''
      Write-Host "  fetching with stacks='$Stacks' (library@$LibraryRef)..." -ForegroundColor DarkGray
      python -c "from conductor.rag import bootstrap; bootstrap._fetch_repo_corpus()" |
        ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
      $all = @(Get-ChildItem -Recurse -Filter *.md -Path $libdir -ErrorAction SilentlyContinue)
      Write-Host ("  downloaded {0} books to disk:" -f $all.Count) -ForegroundColor Green
      Get-ChildItem -Directory $libdir -ErrorAction SilentlyContinue | Sort-Object Name | ForEach-Object {
        $n = @(Get-ChildItem $_.FullName -Filter *.md -ErrorAction SilentlyContinue).Count
        if ($n) { Write-Host ("    {0}/  ({1} books)" -f $_.Name, $n) -ForegroundColor Green }
      }
      Write-Host "  stack books that landed (from your '$Stacks'):" -ForegroundColor DarkGray
      Get-ChildItem -Recurse -Filter *.md -Path $libdir | Where-Object {
        $head = (Get-Content $_.FullName -TotalCount 6) -join "`n"
        $head -match 'software_dev:\s*stack'
      } | ForEach-Object { Write-Host "    + $($_.Name)" -ForegroundColor Green }
      Write-Host '  (stacks you did NOT choose are never downloaded)' -ForegroundColor DarkGray
    }
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

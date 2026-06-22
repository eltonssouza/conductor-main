<#
  Conductor installer — Windows (PowerShell).

    irm https://raw.githubusercontent.com/eltonssouza/conductor-main/main/install.ps1 | iex

  Isolated, no admin: installs (or reuses) uv, clones Conductor into a cache, and
  installs the `cdt` / `conductor` commands as an editable uv tool — so the Docker
  backends (`cdt up`, built from the clone) work too. Falls back to pipx if uv is
  unavailable. Idempotent: re-run to update.

  Env overrides: CONDUCTOR_REPO, CONDUCTOR_REF, CONDUCTOR_SRC, CONDUCTOR_EXTRAS
  (default "rag,honcho"; set empty for a core-only install), CONDUCTOR_DRY_RUN=1,
  NO_COLOR=1.
#>
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.UTF8Encoding]::new() } catch {}

$Repo   = if ($env:CONDUCTOR_REPO) { $env:CONDUCTOR_REPO } else { 'https://github.com/eltonssouza/conductor-main.git' }
$Ref    = if ($env:CONDUCTOR_REF)  { $env:CONDUCTOR_REF }  else { 'main' }
$Src    = if ($env:CONDUCTOR_SRC)  { $env:CONDUCTOR_SRC }  else { Join-Path $env:USERPROFILE '.conductor\src' }
$Extras = if ($null -ne $env:CONDUCTOR_EXTRAS) { $env:CONDUCTOR_EXTRAS } else { 'rag,honcho' }
$Dry    = $env:CONDUCTOR_DRY_RUN -eq '1'
$NoColor = [bool]$env:NO_COLOR

function Glyph($sym, $color, $text) {
  if ($NoColor) { Write-Host "$sym $text" }
  else { Write-Host "$sym " -ForegroundColor $color -NoNewline; Write-Host $text }
}
function Step($t) { Glyph '→' 'Cyan'   $t }
function Ok($t)   { Glyph '✓' 'Green'  $t }
function Warn($t) { Glyph '!' 'Yellow' $t }
function Err($t)  { Glyph '✗' 'Red'    $t }
function Dim($t)  { if ($NoColor) { Write-Host "  $t" } else { Write-Host "  $t" -ForegroundColor DarkGray } }
function Die($t)  { Err $t; exit 1 }
function Have($n) { [bool](Get-Command $n -ErrorAction SilentlyContinue) }

# run a (potentially mutating) command, honoring dry-run.
function Run([scriptblock]$Block, [string]$Label) {
  if ($Dry) { Dim "(dry-run) $Label"; return }
  & $Block
}

function Banner {
  $c = if ($NoColor) { 'Gray' } else { 'Cyan' }
  Write-Host ''
  Write-Host '╔══════════════════════════════════════════╗' -ForegroundColor $c
  Write-Host '║  # Conductor Installer                    ║' -ForegroundColor $c
  Write-Host '║  conduct your project through 11 gates    ║' -ForegroundColor $c
  Write-Host '╚══════════════════════════════════════════╝' -ForegroundColor $c
  Write-Host ''
}

Banner

# [1/5] prerequisites ---------------------------------------------------------
Step "Checking environment (Windows)..."
if (-not (Have git)) { Die "git not found. Install Git for Windows (https://git-scm.com/download/win) or 'winget install Git.Git', then re-run." }
Ok ("git " + ((git --version) -replace 'git version ',''))

# [2/5] ensure uv (isolated, can manage Python) — fall back to pipx -----------
$Pm = ''
if (Have uv) {
  Ok ("uv " + ((uv --version) -replace 'uv ','') + " (already installed)")
  $Pm = 'uv'
} else {
  Step "Installing uv (Astral — isolated, no admin)..."
  Run { Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression } "install uv"
  $uvBin = Join-Path $env:USERPROFILE '.local\bin'
  if (Test-Path (Join-Path $uvBin 'uv.exe')) { $env:Path = "$uvBin;$env:Path" }
  if (Have uv) { Ok "uv installed"; $Pm = 'uv' }
}
if (-not $Pm) {
  Warn "uv unavailable — falling back to pipx"
  if (-not (Have pipx)) {
    if (-not (Have python)) { Die "neither uv, pipx, nor python found. Install Python 3.9+ (https://python.org) or uv, then re-run." }
    Step "Bootstrapping pipx via python..."
    Run { python -m pip install --user pipx } "pip install pipx"
    Run { python -m pipx ensurepath } "pipx ensurepath"
  }
  if (-not (Have pipx)) { Die "could not install pipx. Install uv (https://astral.sh/uv) or pipx manually, then re-run." }
  Ok "pipx ready"
  $Pm = 'pipx'
}

# [3/5] clone (or update) the source -----------------------------------------
if (Test-Path (Join-Path $Src '.git')) {
  Step "Updating Conductor source at $Src..."
  Run { git -C $Src fetch --depth 1 origin $Ref } "git fetch"
  Run { git -C $Src checkout -q $Ref } "git checkout"
  Run { git -C $Src reset --hard -q "origin/$Ref" } "git reset"
} else {
  Step "Cloning Conductor into $Src..."
  Run { New-Item -ItemType Directory -Force -Path (Split-Path $Src) | Out-Null } "mkdir"
  Run { git clone --depth 1 --branch $Ref $Repo $Src } "git clone"
}
Ok "source ready ($Repo@$Ref)"

# [4/5] install the cdt / conductor commands (editable) ----------------------
$spec = if ($Extras) { "$Src[$Extras]" } else { $Src }
Step ("Installing the cdt CLI via $Pm" + $(if ($Extras) { " (extras: $Extras)" } else { '' }) + "...")
if ($Pm -eq 'uv') {
  try { Run { uv tool install --force --editable $spec } "uv tool install $spec" }
  catch { Warn "install with extras failed — retrying core-only"; Run { uv tool install --force --editable $Src } "uv tool install core" }
  try { Run { uv tool update-shell } "uv tool update-shell" } catch {}
} else {
  try { Run { pipx install --force --editable $spec } "pipx install $spec" }
  catch { Warn "install with extras failed — retrying core-only"; Run { pipx install --force --editable $Src } "pipx install core" }
  try { Run { pipx ensurepath } "pipx ensurepath" } catch {}
}
Ok "cdt installed"

# [5/5] verify ---------------------------------------------------------------
Step "Verifying..."
$cdtExe = $null
if (Have cdt) { $cdtExe = 'cdt' }
elseif (Test-Path (Join-Path $env:USERPROFILE '.local\bin\cdt.exe')) { $cdtExe = Join-Path $env:USERPROFILE '.local\bin\cdt.exe' }

if ($Dry) {
  Ok "dry-run complete — no changes made"
} elseif ($cdtExe) {
  try { & $cdtExe --help *> $null; Ok "cdt is working" }
  catch { Warn "cdt installed but not on this shell's PATH yet — open a new terminal" }
} else {
  Warn "cdt installed but not on this shell's PATH yet — open a new terminal"
}

# done -----------------------------------------------------------------------
Write-Host ''
Write-Host 'Conductor installed.' -ForegroundColor White -NoNewline; Write-Host ' Next:'
Dim 'cdt init                 # scaffold roles + guide into a project'
Dim 'cdt up                   # start the RAG + diary backends (Docker)'
Dim 'cdt --help               # all commands'
if (-not $Extras) { Dim "(core-only: add 'cdt library'/'journal recall' later with CONDUCTOR_EXTRAS=rag,honcho)" }
Write-Host ''

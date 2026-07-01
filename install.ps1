<#
  Conductor installer - Windows (PowerShell).

    irm https://raw.githubusercontent.com/eltonssouza/conductor-main/main/install.ps1 | iex

  Isolated, no admin: installs (or reuses) uv, then installs the `cdt` /
  `conductor` commands as a real package straight from the public repo (pip's
  git+https support) - NO source clone on the host. The Docker backends
  (`cdt up`) fetch their own build context from the repo, so a clone is not
  needed there either. Falls back to pipx if uv is unavailable. Idempotent:
  re-run to update.

  Env overrides: CONDUCTOR_REPO, CONDUCTOR_REF, CONDUCTOR_EXTRAS
  (default "rag,honcho"; set "none" for a core-only install), CONDUCTOR_DRY_RUN=1,
  CONDUCTOR_NO_PATH=1 (skip PATH edit), NO_COLOR=1.

  NOTE: this file is ASCII with NO BOM on purpose, so `irm <url> | iex` parses it.
  The status glyphs are built from char codes at runtime, not stored as literals.
#>
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.UTF8Encoding]::new() } catch {}

$Repo   = if ($env:CONDUCTOR_REPO) { $env:CONDUCTOR_REPO } else { 'https://github.com/eltonssouza/conductor-main.git' }
$Ref    = if ($env:CONDUCTOR_REF)  { $env:CONDUCTOR_REF }  else { 'main' }
$Extras = if ($null -ne $env:CONDUCTOR_EXTRAS) { $env:CONDUCTOR_EXTRAS } else { 'rag,honcho' }
if ($Extras -in @('none','core','')) { $Extras = '' }   # core-only (PS env can't hold "")
$Dry    = $env:CONDUCTOR_DRY_RUN -eq '1'
$NoColor = [bool]$env:NO_COLOR
$NoPath  = $env:CONDUCTOR_NO_PATH -eq '1'

# Status glyphs built from code points (keeps this source pure ASCII / BOM-free).
$G_OK   = [char]0x2713   # check mark
$G_STEP = [char]0x2192   # right arrow
$G_ERR  = [char]0x2717   # ballot x

function Glyph($sym, $color, $text) {
  if ($NoColor) { Write-Host "$sym $text" }
  else { Write-Host "$sym " -ForegroundColor $color -NoNewline; Write-Host $text }
}
function Step($t) { Glyph $G_STEP 'Cyan'   $t }
function Ok($t)   { Glyph $G_OK   'Green'  $t }
function Warn($t) { Glyph '!'     'Yellow' $t }
function Err($t)  { Glyph $G_ERR  'Red'    $t }
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
  Write-Host '  ===========================================' -ForegroundColor $c
  Write-Host '   # Conductor Installer' -ForegroundColor $c
  Write-Host '   conduct your project through 12 gates' -ForegroundColor $c
  Write-Host '  ===========================================' -ForegroundColor $c
  Write-Host ''
}

Banner

# [1/4] prerequisites ---------------------------------------------------------
Step "Checking environment (Windows)..."
if (-not (Have git)) { Die "git not found. Install Git for Windows (https://git-scm.com/download/win) or 'winget install Git.Git', then re-run." }
Ok ("git " + ((git --version) -replace 'git version ',''))

# [2/4] ensure uv (isolated, can manage Python) - fall back to pipx -----------
$Pm = ''
if (Have uv) {
  Ok ("uv " + ((uv --version) -replace 'uv ','') + " (already installed)")
  $Pm = 'uv'
} else {
  Step "Installing uv (Astral - isolated, no admin)..."
  Run { Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression } "install uv"
  $uvBin = Join-Path $env:USERPROFILE '.local\bin'
  if (Test-Path (Join-Path $uvBin 'uv.exe')) { $env:Path = "$uvBin;$env:Path" }
  if (Have uv) { Ok "uv installed"; $Pm = 'uv' }
}
if (-not $Pm) {
  Warn "uv unavailable - falling back to pipx"
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

# [3/4] install the cdt / conductor commands from the repo (no host clone) ---
# pip's PEP 508 direct-reference form: `conductor[extras] @ git+URL@ref`.
$core = "conductor @ git+$Repo@$Ref"
$spec = if ($Extras) { "conductor[$Extras] @ git+$Repo@$Ref" } else { $core }
Step ("Installing the cdt CLI via $Pm" + $(if ($Extras) { " (extras: $Extras)" } else { '' }) + "...")
if ($Pm -eq 'uv') {
  try { Run { uv tool install --force $spec } "uv tool install $spec" }
  catch { Warn "install with extras failed - retrying core-only"; Run { uv tool install --force $core } "uv tool install core" }
  if (-not $NoPath) { try { Run { uv tool update-shell } "uv tool update-shell" } catch {} }
} else {
  try { Run { pipx install --force $spec } "pipx install $spec" }
  catch { Warn "install with extras failed - retrying core-only"; Run { pipx install --force $core } "pipx install core" }
  if (-not $NoPath) { try { Run { pipx ensurepath } "pipx ensurepath" } catch {} }
}
Ok "cdt installed"

# [4/4] verify ---------------------------------------------------------------
Step "Verifying..."
$cdtExe = $null
if (Have cdt) { $cdtExe = 'cdt' }
elseif (Test-Path (Join-Path $env:USERPROFILE '.local\bin\cdt.exe')) { $cdtExe = Join-Path $env:USERPROFILE '.local\bin\cdt.exe' }

if ($Dry) {
  Ok "dry-run complete - no changes made"
} elseif ($cdtExe) {
  try { & $cdtExe --help *> $null; Ok "cdt is working" }
  catch { Warn "cdt installed but not on this shell's PATH yet - open a new terminal" }
} else {
  Warn "cdt installed but not on this shell's PATH yet - open a new terminal"
}

# done -----------------------------------------------------------------------
Write-Host ''
Write-Host 'Conductor installed.' -ForegroundColor White -NoNewline; Write-Host ' Next:'
Dim 'cdt init                 # scaffold roles + guide into a project'
Dim 'cdt up                   # start the RAG + diary backends (Docker)'
Dim 'cdt --help               # all commands'
if (-not $Extras) { Dim "(core-only: add 'cdt library'/'journal recall' later with CONDUCTOR_EXTRAS=rag,honcho)" }
Write-Host ''

#!/usr/bin/env sh
# Conductor installer — POSIX (macOS / Linux).
#
#   curl -fsSL https://raw.githubusercontent.com/eltonssouza/conductor-main/main/install.sh | sh
#
# Isolated, no sudo: installs (or reuses) uv, then installs the `cdt` /
# `conductor` commands as a real package straight from the public repo (pip's
# git+https support) — NO source clone on the host. The Docker backends
# (`cdt up`) fetch their own build context from the repo, so a clone is not
# needed there either. Falls back to pipx if uv is unavailable. Idempotent:
# re-run to update.
#
# Env overrides: CONDUCTOR_REPO, CONDUCTOR_REF, CONDUCTOR_EXTRAS (default
# "rag,honcho"; set empty for a core-only install), CONDUCTOR_DRY_RUN=1,
# NO_COLOR=1.
set -eu

REPO="${CONDUCTOR_REPO:-https://github.com/eltonssouza/conductor-main.git}"
REF="${CONDUCTOR_REF:-main}"
EXTRAS="${CONDUCTOR_EXTRAS-rag,honcho}"
case "$EXTRAS" in none|core) EXTRAS="" ;; esac   # 'none'/'core' (or empty) -> core-only
DRY="${CONDUCTOR_DRY_RUN:-0}"
NOPATH="${CONDUCTOR_NO_PATH:-0}"   # skip PATH modification (used by the sandbox simulator)

# --- styling: ANSI colors + Unicode status glyphs (TTY only, honor NO_COLOR) ---
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  C_RESET="$(printf '\033[0m')"; C_DIM="$(printf '\033[2m')"
  C_GREEN="$(printf '\033[32m')"; C_RED="$(printf '\033[31m')"
  C_YELLOW="$(printf '\033[33m')"; C_CYAN="$(printf '\033[36m')"
  C_BOLD="$(printf '\033[1m')"
else
  C_RESET=""; C_DIM=""; C_GREEN=""; C_RED=""; C_YELLOW=""; C_CYAN=""; C_BOLD=""
fi

step() { printf '%s→%s %s\n' "$C_CYAN" "$C_RESET" "$1"; }
ok()   { printf '%s✓%s %s\n' "$C_GREEN" "$C_RESET" "$1"; }
warn() { printf '%s!%s %s\n' "$C_YELLOW" "$C_RESET" "$1"; }
err()  { printf '%s✗%s %s\n' "$C_RED" "$C_RESET" "$1" >&2; }
dim()  { printf '%s  %s%s\n' "$C_DIM" "$1" "$C_RESET"; }
die()  { err "$1"; exit 1; }

banner() {
  printf '\n%s╔══════════════════════════════════════════╗%s\n' "$C_CYAN" "$C_RESET"
  printf '%s║%s  %s# Conductor Installer%s                   %s║%s\n' \
    "$C_CYAN" "$C_RESET" "$C_BOLD" "$C_RESET" "$C_CYAN" "$C_RESET"
  printf '%s║%s  %sconduct your project through 12 gates%s   %s║%s\n' \
    "$C_CYAN" "$C_RESET" "$C_DIM" "$C_RESET" "$C_CYAN" "$C_RESET"
  printf '%s╚══════════════════════════════════════════╝%s\n\n' "$C_CYAN" "$C_RESET"
}

# run a (potentially mutating) command, honoring dry-run.
run() {
  if [ "$DRY" = "1" ]; then dim "(dry-run) $*"; return 0; fi
  "$@"
}

have() { command -v "$1" >/dev/null 2>&1; }

# --- error trap: any unexpected failure prints a clear ✗ ---------------------
trap 'st=$?; [ "$st" -ne 0 ] && err "install aborted (exit $st)"; exit $st' EXIT INT TERM

banner

# [1/4] OS + prerequisites ----------------------------------------------------
OS="$(uname -s 2>/dev/null || echo unknown)"
step "Checking environment (${OS})..."
have git || die "git not found. Install git first (e.g. 'xcode-select --install' on macOS, or your distro's package), then re-run."
ok "git $(git --version 2>/dev/null | awk '{print $3}')"

# [2/4] ensure uv (fast, isolated; can manage Python) — fall back to pipx ------
PM=""
if have uv; then
  ok "uv $(uv --version 2>/dev/null | awk '{print $2}') (already installed)"
  PM="uv"
else
  step "Installing uv (Astral — isolated, no sudo)..."
  if run sh -c 'curl -LsSf https://astral.sh/uv/install.sh | sh' && have uv; then
    ok "uv installed"
    PM="uv"
  else
    # uv install needs the freshly-added PATH this shell may not see yet
    if [ -x "${HOME}/.local/bin/uv" ]; then PATH="${HOME}/.local/bin:${PATH}"; export PATH; fi
    if have uv; then ok "uv installed"; PM="uv"; fi
  fi
fi
if [ -z "$PM" ]; then
  warn "uv unavailable — falling back to pipx"
  have pipx || have python3 || die "neither uv, pipx, nor python3 found. Install Python 3.9+ or uv, then re-run."
  if ! have pipx; then
    step "Bootstrapping pipx via python3..."
    run python3 -m pip install --user pipx
    run python3 -m pipx ensurepath
  fi
  have pipx || { [ -x "${HOME}/.local/bin/pipx" ] && PATH="${HOME}/.local/bin:${PATH}" && export PATH; }
  have pipx || die "could not install pipx. Install uv (https://astral.sh/uv) or pipx manually, then re-run."
  ok "pipx ready"
  PM="pipx"
fi

# [3/4] install the cdt / conductor commands from the repo (no host clone) ----
# pip's PEP 508 direct-reference form: `conductor[extras] @ git+URL@ref`.
core="conductor @ git+${REPO}@${REF}"
spec="$core"
[ -n "$EXTRAS" ] && spec="conductor[${EXTRAS}] @ git+${REPO}@${REF}"
step "Installing the cdt CLI via ${PM}${EXTRAS:+ (extras: ${EXTRAS})}..."
if [ "$PM" = "uv" ]; then
  if ! run uv tool install --force "$spec"; then
    warn "install with extras failed — retrying core-only"
    run uv tool install --force "$core"
  fi
  [ "$NOPATH" = "1" ] || run uv tool update-shell || true
else
  if ! run pipx install --force "$spec"; then
    warn "install with extras failed — retrying core-only"
    run pipx install --force "$core"
  fi
  [ "$NOPATH" = "1" ] || run pipx ensurepath || true
fi
ok "cdt installed"

# [4/4] verify ----------------------------------------------------------------
step "Verifying..."
CDT=""
if have cdt; then CDT="cdt"
elif [ -x "${HOME}/.local/bin/cdt" ]; then CDT="${HOME}/.local/bin/cdt"; fi

if [ "$DRY" = "1" ]; then
  ok "dry-run complete — no changes made"
elif [ -n "$CDT" ] && "$CDT" --help >/dev/null 2>&1; then
  ok "cdt is working"
else
  warn "cdt installed but not on this shell's PATH yet — open a new terminal (or 'source' your shell profile)"
fi

# done ------------------------------------------------------------------------
trap - EXIT INT TERM
printf '\n%sConductor installed.%s Next:\n' "$C_BOLD" "$C_RESET"
dim "cdt init                 # scaffold roles + guide into a project"
dim "cdt up                   # start the RAG + diary backends (Docker)"
dim "cdt --help               # all commands"
[ -z "$EXTRAS" ] && dim "(core-only: add 'cdt library'/'journal recall' later with CONDUCTOR_EXTRAS=rag,honcho)"
printf '\n'

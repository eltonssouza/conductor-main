#!/usr/bin/env python3
"""`python -m cdt.honcho_setup` — choose the Honcho reasoning provider.

The provider that powers Honcho's background reasoning (deriver + dialectic +
summary) is **not baked in** — you pick it at install time. This writes
`infra/honcho/.env` for the chosen provider; any OpenAI-compatible endpoint
works (OpenAI, DeepSeek, OpenRouter, local Ollama/vLLM…), plus native Anthropic.

  python -m cdt.honcho_setup                         # interactive
  python -m cdt.honcho_setup --provider deepseek     # non-interactive
  python -m cdt.honcho_setup --provider ollama       # local, no key needed
  python -m cdt.honcho_setup --provider openai --model gpt-4o --api-key sk-...
  python -m cdt.honcho_setup --provider custom \
      --base-url https://my-gateway/v1 --model my-model --api-key sk-...
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

from .project import PACKAGE_INFRA, force_utf8

FEATURES = ("DERIVER", "DIALECTIC", "SUMMARY")

# Per-provider key-file convenience. For provider X, if no key is supplied another
# way, Conductor reads the first token-looking value from `~/.conductor/X-key.txt`
# (override the path with CONDUCTOR_<PROVIDER>_API_KEY_FILE). The file is a simple
# `NAME: "value"` / `NAME=value` / bare-token text file. Backward compatible: the
# legacy DeepSeek file `~/.conductor/deepseek-key.txt` (var `API-KEY-DEEP_SEEK`,
# overridable via CONDUCTOR_DEEPSEEK_KEY_FILE) is still honored.
DEEPSEEK_KEY_VAR = "API-KEY-DEEP_SEEK"

# Token shapes accepted from a key file or env var. An `sk-...` token (OpenAI /
# OpenRouter `sk-or-...` / Anthropic `sk-ant-...`) is preferred when present, so a
# line like `API-KEY-DEEP_SEEK: "sk-..."` yields the token, not the var name.
_SK_RE = re.compile(r"(sk-[A-Za-z0-9_\-]+)")
# Fallback for providers whose keys are opaque (no `sk-` prefix), e.g. a bare
# token on its own line or `NAME=token`.
_TOKEN_RE = re.compile(r"=\s*([A-Za-z0-9][A-Za-z0-9_\-]{15,})|^\s*([A-Za-z0-9][A-Za-z0-9_\-]{15,})\s*$")


def _key_file_for(provider: str) -> Path:
    """Per-provider key-file path, overridable via env.

    Resolution: CONDUCTOR_<PROVIDER>_API_KEY_FILE, then (deepseek only) the legacy
    CONDUCTOR_DEEPSEEK_KEY_FILE, then the default `~/.conductor/<provider>-key.txt`.
    """
    up = provider.upper()
    env = os.environ.get(f"CONDUCTOR_{up}_API_KEY_FILE")
    if not env and provider == "deepseek":
        env = os.environ.get("CONDUCTOR_DEEPSEEK_KEY_FILE")
    if env:
        return Path(env)
    return Path.home() / ".conductor" / f"{provider}-key.txt"


def _read_key_from_file(path: Path, var: Optional[str] = None) -> Optional[str]:
    """Reads a key token from a simple text file.

    If `var` is given, the first line containing `var` wins; otherwise the first
    line that yields a token wins. Accepts `NAME: "tok"`, `NAME=tok`, or a bare
    token on its own line. Returns None if the file is missing/unreadable.
    """
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    # Prefer a line that mentions `var` when one is requested (back-compat).
    candidates = [ln for ln in lines if var and var in ln] or lines
    for line in candidates:
        body = line.split("#", 1)[0]
        m = _SK_RE.search(body)
        if m:
            return m.group(1)
        m = _TOKEN_RE.search(body)
        if m:
            return m.group(1) or m.group(2)
    return None


def _resolve_key(provider: str, preset: dict, cli_key: Optional[str]) -> Optional[str]:
    """Key resolution order, highest precedence first:
    1. `--api-key` on the command line
    2. env var `CONDUCTOR_<PROVIDER>_API_KEY` (or the preset's `key_env`)
    3. per-provider key file `~/.conductor/<provider>-key.txt`
       (override: `CONDUCTOR_<PROVIDER>_API_KEY_FILE`; legacy deepseek file honored)
    4. None — caller falls back to interactive prompt / placeholder
    """
    if cli_key:
        return cli_key
    up = provider.upper()
    env_key = os.environ.get(f"CONDUCTOR_{up}_API_KEY") or os.environ.get(preset["key_env"])
    if env_key:
        return env_key
    # The legacy deepseek file is matched against its named var; others take the
    # first token on any line.
    var = DEEPSEEK_KEY_VAR if provider == "deepseek" else None
    file_key = _read_key_from_file(_key_file_for(provider), var)
    if file_key:
        print(f"{provider} key loaded from {_key_file_for(provider)}")
        return file_key
    return None


# Each preset is OpenAI-compatible unless transport says otherwise. base_url
# empty = use the provider's native default. `custom` has no baked-in endpoint —
# supply --base-url (+ --model, --api-key) for any OpenAI-compatible gateway
# (vLLM, LM Studio, Groq, Together, a local proxy, …).
PRESETS: Dict[str, dict] = {
    "openai": {"transport": "openai", "base_url": "https://api.openai.com/v1",
               "model": "gpt-4o-mini", "key_env": "LLM_OPENAI_API_KEY",
               "needs_key": True},
    "deepseek": {"transport": "openai", "base_url": "https://api.deepseek.com/v1",
                 "model": "deepseek-chat", "key_env": "LLM_OPENAI_API_KEY",
                 "needs_key": True},
    "openrouter": {"transport": "openai", "base_url": "https://openrouter.ai/api/v1",
                   "model": "google/gemini-2.5-flash", "key_env": "LLM_OPENAI_API_KEY",
                   "needs_key": True},
    "ollama": {"transport": "openai", "base_url": "http://host.docker.internal:11434/v1",
               "model": "llama3.1", "key_env": "LLM_OPENAI_API_KEY",
               "needs_key": False},  # local: any dummy key
    "anthropic": {"transport": "anthropic", "base_url": "",
                  "model": "claude-haiku-4-5", "key_env": "LLM_ANTHROPIC_API_KEY",
                  "needs_key": True},
    "custom": {"transport": "openai", "base_url": "",
               "model": "", "key_env": "LLM_OPENAI_API_KEY",
               "needs_key": True},  # any OpenAI-compatible endpoint via --base-url
}


def render_env(provider: str, model: str, base_url: str, api_key: str,
               key_env: str, transport: str) -> str:
    lines: List[str] = [
        f"# Honcho reasoning provider: {provider} (generated by cdt honcho-setup).",
        "# Re-run `cdt honcho-setup` to switch providers.",
        "",
        f"{key_env}={api_key}",
    ]
    # Global default base URL: routes any LLM call WITHOUT a per-feature override
    # (e.g. the dialectic tool-loop) to the chosen endpoint instead of OpenAI.
    if transport == "openai" and base_url:
        lines.append(f"LLM_OPENAI_BASE_URL={base_url}")
    lines.append("")
    for feat in FEATURES:
        lines.append(f"{feat}_MODEL_CONFIG__TRANSPORT={transport}")
        lines.append(f"{feat}_MODEL_CONFIG__MODEL={model}")
        if base_url:
            lines.append(f"{feat}_MODEL_CONFIG__OVERRIDES__BASE_URL={base_url}")
        lines.append("")

    # The dialectic does NOT use DIALECTIC_MODEL_CONFIG; it uses per-reasoning-level
    # configs (each defaulting to the vendor's own model). Override every level so
    # the dialectic tool-loop actually uses the chosen provider/model.
    for lvl in ("minimal", "low", "medium", "high", "max"):
        lines.append(f"DIALECTIC_LEVELS__{lvl}__MODEL_CONFIG__TRANSPORT={transport}")
        lines.append(f"DIALECTIC_LEVELS__{lvl}__MODEL_CONFIG__MODEL={model}")
        if base_url:
            lines.append(f"DIALECTIC_LEVELS__{lvl}__MODEL_CONFIG__OVERRIDES__BASE_URL={base_url}")
    lines.append("")

    # Honcho also EMBEDS messages for vector recall. DeepSeek/Anthropic/OpenRouter
    # have no (compatible) embeddings, so default embeddings to the local Ollama
    # bge-m3 unless the provider is OpenAI itself.
    if provider == "openai":
        embed_model, embed_url, embed_dims = "text-embedding-3-small", base_url, 1536
    else:
        embed_model = "bge-m3"
        embed_url = "http://host.docker.internal:11434/v1"
        embed_dims = 1024  # bge-m3 is 1024-d
    lines.append(f"EMBEDDING_MODEL_CONFIG__TRANSPORT=openai")
    lines.append(f"EMBEDDING_MODEL_CONFIG__MODEL={embed_model}")
    lines.append(f"EMBEDDING_MODEL_CONFIG__OVERRIDES__BASE_URL={embed_url}")
    # Vector column dimension (the DB is created with this; a fresh volume is
    # needed if you change it). Ollama rejects the OpenAI `dimensions=` param.
    lines.append(f"EMBEDDING_VECTOR_DIMENSIONS={embed_dims}")
    if provider != "openai":
        lines.append("EMBEDDING_MODEL_CONFIG__DIMENSIONS_MODE=never")
    lines.append("")

    lines.append("# Self-host: no auth (the API binds to localhost only).")
    lines.append("AUTH_USE_AUTH=false")
    return "\n".join(lines) + "\n"


def _prompt_choice() -> str:
    names = list(PRESETS)
    print("Choose the Honcho reasoning provider:")
    for i, name in enumerate(names, 1):
        p = PRESETS[name]
        if name == "ollama":
            loc, model = "local, no key", p["model"]
        elif name == "custom":
            loc, model = "your --base-url", "any OpenAI-compatible"
        else:
            loc, model = (p["base_url"] or "native"), p["model"]
        print(f"  {i}. {name:<11} ({model}, {loc})")
    raw = input(f"Provider [1-{len(names)}] (default 1): ").strip()
    if not raw:
        return names[0]
    if raw.isdigit() and 1 <= int(raw) <= len(names):
        return names[int(raw) - 1]
    if raw in PRESETS:
        return raw
    print(f"Unknown choice '{raw}'.", file=sys.stderr)
    raise SystemExit(2)


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Configure Honcho's reasoning provider.")
    ap.add_argument("--provider", choices=list(PRESETS), help="provider preset")
    ap.add_argument("--model", help="override the model id")
    ap.add_argument("--base-url", help="override the OpenAI-compatible base URL")
    ap.add_argument("--api-key", help="API key (or set it later in the .env)")
    ap.add_argument("--out", type=Path, default=None,
                    help="output .env path (default: the staged Honcho infra dir)")
    ap.add_argument("--force", action="store_true", help="overwrite an existing .env")
    args = ap.parse_args(argv)
    force_utf8()

    out = args.out or (PACKAGE_INFRA / "honcho" / ".env")

    provider = args.provider or _prompt_choice()
    preset = PRESETS[provider]
    model = args.model or preset["model"]
    base_url = preset["base_url"] if args.base_url is None else args.base_url
    transport = preset["transport"]
    key_env = preset["key_env"]

    if provider == "custom" and not base_url:
        print("--provider custom needs --base-url <openai-compatible-url>.",
              file=sys.stderr)
        return 2
    if provider == "custom" and not model:
        print("--provider custom needs --model <id>.", file=sys.stderr)
        return 2

    api_key = _resolve_key(provider, preset, args.api_key)
    if api_key is None:
        if preset["needs_key"]:
            if sys.stdin.isatty():
                api_key = input(f"{provider} API key (blank = fill in later): ").strip()
            api_key = api_key or f"set-your-{provider}-key"
        else:
            api_key = "ollama"  # local: any value

    if out.exists() and not args.force:
        print(f"{out} exists (use --force to overwrite).", file=sys.stderr)
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_env(provider, model, base_url, api_key, key_env, transport),
                   encoding="utf-8")

    print(f"Wrote {out} (provider: {provider}, model: {model}).")
    print(f"  Honcho infra staged at: {out.parent}  (run `docker compose up -d` there)")
    if api_key.startswith("set-your-"):
        print(f"  -> edit {out} and set {key_env} before `docker compose up`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

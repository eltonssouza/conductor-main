"""Thin, defensive wrapper over the Honcho SDK for the development diary.

Honcho (https://honcho.dev) is the long-term memory: it stores the diary
messages and reasons over them in the background (peer modeling + dialectic),
so `recall` can answer by meaning. This module never raises into the caller —
every SDK interaction is guarded so the diary keeps working (via the local
JSONL mirror) when the `honcho` package is missing or the server is down.

Peer model (owner decision): two peers per workspace — `conductor` (all AI
roles) and `owner` (the human). Workspace id = the project slug.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

CONDUCTOR_PEER = "conductor"
OWNER_PEER = "owner"


@dataclass
class HonchoResult:
    ok: bool
    detail: str = ""          # error/diagnostic when not ok
    text: Optional[str] = None  # payload for recall


class HonchoBackend:
    """Lazily-constructed Honcho client bound to one project workspace."""

    def __init__(self, workspace: str, base_url: str):
        self.workspace = workspace
        self.base_url = base_url
        self._client = None
        self._error: Optional[str] = None

    @classmethod
    def from_config(cls, config: dict) -> "HonchoBackend":
        h = (config or {}).get("honcho", {})
        return cls(workspace=h.get("workspace") or config.get("project", "project"),
                   base_url=h.get("base_url", "http://localhost:8000"))

    def _connect(self):
        if self._client is not None or self._error is not None:
            return self._client
        try:
            from honcho import Honcho  # optional dependency (extra [honcho])
        except Exception as e:  # noqa: BLE001
            self._error = (f"honcho SDK not installed ({e}); "
                           "install with `pip install -e .[honcho]`")
            return None
        try:
            api_key = os.environ.get("CONDUCTOR_HONCHO_API_KEY", "local")
            base_url = os.environ.get("CONDUCTOR_HONCHO_URL", self.base_url)
            self._client = Honcho(workspace_id=self.workspace,
                                  api_key=api_key, base_url=base_url)
        except Exception as e:  # noqa: BLE001
            self._error = f"cannot reach Honcho at {self.base_url} ({e})"
            self._client = None
        return self._client

    def add(self, session_id: str, text: str, *, gate: Optional[int],
            kind: str, as_owner: bool = False) -> HonchoResult:
        client = self._connect()
        if client is None:
            return HonchoResult(False, self._error or "Honcho unavailable")
        try:
            peer = client.peer(OWNER_PEER if as_owner else CONDUCTOR_PEER)
            session = client.session(session_id)
            meta = {"kind": kind}
            if gate is not None:
                meta["gate"] = gate
            try:
                msg = peer.message(text, metadata=meta)
            except TypeError:           # older SDK: no metadata kwarg
                msg = peer.message(text)
            session.add_messages([msg])
            return HonchoResult(True)
        except Exception as e:  # noqa: BLE001
            return HonchoResult(False, f"Honcho add failed ({e})")

    def recall(self, session_id: str, question: str) -> HonchoResult:
        client = self._connect()
        if client is None:
            return HonchoResult(False, self._error or "Honcho unavailable")
        try:
            peer = client.peer(CONDUCTOR_PEER)
            # Prefer a session-scoped dialectic query; the kwarg name varies by
            # SDK version, so fall back to a plain global chat on any rejection.
            answer = None
            for kwargs in ({"session_id": session_id}, {"session": session_id}, {}):
                try:
                    answer = peer.chat(question, **kwargs)
                    break
                except Exception:  # noqa: BLE001 — try the next call shape
                    continue
            return HonchoResult(True, text=str(answer) if answer else None)
        except Exception as e:  # noqa: BLE001
            return HonchoResult(False, f"Honcho recall failed ({e})")

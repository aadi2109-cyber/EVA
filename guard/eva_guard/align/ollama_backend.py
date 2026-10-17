"""
ALIGN backend for LAYA served by Ollama's System-1 endpoint:

    POST {OLLAMA_HOST}/v1/systemone
    {"model": "laya", "state": "<text>", "questions": {"<id>": {"type": "noul", "instructions": "...", "criteria": {"true": "...", "false": "..."}}}}

The request shape is the documented one; the RESPONSE shape has not been seen by SEC-2, so parsing is tolerant
(answers may be nested under "answers", values may be bool / "true" / {"answer": ...}) and anything unrecognised
becomes "unavailable". Advisory only; inputs are the user's request and the proposed action, never retrieved content.
Env: OLLAMA_HOST (default http://127.0.0.1:11434), ALIGN_OLLAMA_MODEL (default "laya"), ALIGN_TIMEOUT_MS.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from contracts.models import AlignVerdict

from .laya_backend import QUESTIONS, build_state, verdict_from_answers

logger = logging.getLogger(__name__)


def _host() -> str:
    h = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").strip()
    return h if h.startswith("http") else f"http://{h}"


def extract_answers(payload: Any) -> dict[str, Any]:
    """Find the {question_id: answer} mapping in whatever envelope the server used."""
    if not isinstance(payload, dict):
        return {}
    for key in ("answers", "result", "results", "decision", "decisions", "output"):
        inner = payload.get(key)
        if isinstance(inner, dict) and any(q in inner for q in QUESTIONS):
            return inner
        if isinstance(inner, dict):
            deeper = extract_answers(inner)
            if deeper:
                return deeper
    return payload if any(q in payload for q in QUESTIONS) else {}


class OllamaAlignBackend:
    def __init__(self, host: str | None = None, model: str | None = None, timeout_ms: int | None = None,
                 transport: httpx.BaseTransport | None = None) -> None:
        self.host = (host or _host()).rstrip("/")
        self.model = model or os.getenv("ALIGN_OLLAMA_MODEL", "laya")
        self.timeout_s = (timeout_ms if timeout_ms is not None else int(os.getenv("ALIGN_TIMEOUT_MS", "1500"))) / 1000
        self._transport = transport

    def raw(self, state: str) -> Any:
        """Unparsed server response (used by the probe)."""
        with httpx.Client(timeout=self.timeout_s, transport=self._transport) as c:
            r = c.post(f"{self.host}/v1/systemone", json={"model": self.model, "state": state, "questions": QUESTIONS})
            r.raise_for_status()
            return r.json()

    def __call__(self, original_request: str, policy: Any, tool: str, args: dict[str, Any]) -> AlignVerdict:
        try:
            payload = self.raw(build_state(original_request, tool, args))
            return verdict_from_answers(extract_answers(payload))
        except Exception as e:  # noqa: BLE001 - connection refused, timeout, HTTP error, bad JSON
            logger.warning("Ollama LAYA ALIGN backend unavailable: %s", e)
            return AlignVerdict(verdict="unavailable", score=None)

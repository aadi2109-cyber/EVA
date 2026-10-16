"""
Gmail backends behind ONE interface (GmailBackend). The tools in gmail.py never know
which one they talk to; GMAIL_MODE=mock|real selects it per call.

Normalised message dict (identical shape from both backends):
  {id, thread_id, from, to, date, subject, snippet, body_plain, body_html}
"""

from __future__ import annotations

import base64
import json
import re
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Protocol

import httpx

from app.config import settings
from app.connectors.gmail_oauth import (
    GMAIL_API_BASE,
    ReconnectNeeded,
    get_access_token,
    google_client,
    invalidate_access_token,
)
from app.tools.htmltext import looks_like_html
from env.mock.state import state as mock_state

_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,128}$")


class GmailBackend(Protocol):
    async def search(self, query: str, max_results: int) -> list[dict[str, Any]]: ...
    async def read(self, message_id: str) -> dict[str, Any]: ...
    async def create_draft(self, to: str, subject: str, body: str) -> dict[str, Any]: ...
    async def send(self, to: str, subject: str, body: str, draft_id: str | None) -> dict[str, Any]: ...


# ------------------------------------------------------------------ mock
def load_mock_mailbox() -> list[dict[str, Any]]:
    candidates = [
        Path(__file__).resolve().parents[4] / "env" / "mock" / "mailbox.json",
        Path("env/mock/mailbox.json"),
    ]
    for p in candidates:
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                return []
    return []


def _summary(m: dict[str, Any]) -> dict[str, Any]:
    return {k: m.get(k, "") for k in ("id", "from", "subject", "date", "snippet")}


class MockGmailBackend:
    async def search(self, query: str, max_results: int) -> list[dict[str, Any]]:
        q = query.lower()
        out = []
        for m in load_mock_mailbox():
            hay = f"{m.get('subject', '')} {m.get('from', '')} {m.get('snippet', '')} {m.get('body', '')}".lower()
            if q in hay or q in [lbl.lower() for lbl in m.get("labels", [])]:
                out.append(_summary(m))
                if len(out) >= max_results:
                    break
        return out

    async def read(self, message_id: str) -> dict[str, Any]:
        m = next((x for x in load_mock_mailbox() if x["id"] == message_id), None)
        if not m:
            raise ValueError(f"Gmail message with ID '{message_id}' not found")
        raw = m.get("body", "")
        html = looks_like_html(raw)
        return {
            **_summary(m),
            "thread_id": m.get("thread_id", ""),
            "to": m.get("to", ""),
            "body_plain": "" if html else raw,
            "body_html": raw if html else "",
        }

    async def create_draft(self, to: str, subject: str, body: str) -> dict[str, Any]:
        return mock_state.record_draft(to=to, subject=subject, body=body)

    async def send(self, to: str, subject: str, body: str, draft_id: str | None) -> dict[str, Any]:
        return mock_state.record_sent_mail(to=to, subject=subject, body=body, draft_id=draft_id)


# ------------------------------------------------------------------ real
MAX_MIME_DEPTH = 12            # deeper nesting is hostile/broken: stop descending (flagged)
MAX_MIME_PARTS = 200
MAX_PART_CHARS = 256 * 1024    # per text part
MAX_BODY_CHARS = 512 * 1024    # all text parts together
_CHARSET_RE = re.compile(r"charset\s*=\s*\"?([A-Za-z0-9_.:-]+)", re.I)


def _b64url_decode(data: str, charset: str = "utf-8") -> str:
    raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
    try:
        return raw.decode(charset or "utf-8", errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


class _Walk:
    def __init__(self) -> None:
        self.plain: list[str] = []
        self.html: list[str] = []
        self.parts = 0
        self.chars = 0
        self.notes: list[str] = []  # surfaced in the body so nothing is silently lost

    def note(self, text: str) -> None:
        if text not in self.notes:
            self.notes.append(text)


def _part_charset(payload: dict[str, Any]) -> str:
    for h in payload.get("headers") or []:
        if str(h.get("name", "")).lower() == "content-type":
            m = _CHARSET_RE.search(str(h.get("value", "")))
            if m:
                return m.group(1)
    m = _CHARSET_RE.search(payload.get("mimeType") or "")
    return m.group(1) if m else "utf-8"


def _walk_parts(payload: dict[str, Any], w: "_Walk", depth: int = 0) -> None:
    if not isinstance(payload, dict):
        return
    w.parts += 1
    if w.parts > MAX_MIME_PARTS:
        w.note("[TRUNCATED: too many MIME parts]")
        return
    mime = (payload.get("mimeType") or "").split(";")[0].strip().lower()
    data = (payload.get("body") or {}).get("data")
    if data and not payload.get("filename") and mime in ("text/plain", "text/html"):
        try:
            text = _b64url_decode(data, _part_charset(payload))
        except ValueError:
            text = f"[UNDECODABLE_PART: {mime}]"
        if len(text) > MAX_PART_CHARS:
            text = text[:MAX_PART_CHARS]
            w.note(f"[TRUNCATED: {mime} part exceeded size cap]")
        room = MAX_BODY_CHARS - w.chars
        if len(text) > room:
            text = text[: max(room, 0)]
            w.note("[TRUNCATED: message body exceeded size cap]")
        w.chars += len(text)
        if text:
            (w.plain if mime == "text/plain" else w.html).append(text)
    children = payload.get("parts") or []
    if children and depth >= MAX_MIME_DEPTH:
        w.note("[TRUNCATED: MIME nesting too deep]")
        return
    for part in children if isinstance(children, list) else []:
        _walk_parts(part, w, depth + 1)


def _headers(payload: dict[str, Any]) -> dict[str, str]:
    return {h["name"].lower(): h["value"] for h in payload.get("headers", []) if "name" in h}


class RealGmailBackend:
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id

    async def _request(self, method: str, path: str, *, params=None, json_body=None) -> dict[str, Any]:
        for attempt in (0, 1):
            token, _ = await get_access_token(self.user_id)
            async with google_client(timeout=15.0) as client:
                resp = await client.request(
                    method, f"{GMAIL_API_BASE}{path}", params=params, json=json_body, headers={"Authorization": f"Bearer {token}"}
                )
            if resp.status_code == 401 and attempt == 0:
                invalidate_access_token(self.user_id)
                continue
            break
        if resp.status_code == 401:
            # A freshly refreshed token was still refused: consent was revoked. Flag the account
            # so later calls fail fast with "reconnect needed" instead of looping on Google.
            from app.connectors.gmail_oauth import _load_account, mark_reconnect_needed
            from app.db.database import async_session_factory

            async with async_session_factory() as session:
                acc = await _load_account(session, self.user_id)
                if acc is not None:
                    await mark_reconnect_needed(session, acc, "Google rejected the access token")
            raise ReconnectNeeded()
        if resp.status_code == 404:
            raise ValueError("Gmail message or draft not found")
        if resp.status_code == 403:
            raise PermissionError("Gmail refused the request (insufficient permission or API disabled)")
        if resp.status_code == 429 or resp.status_code >= 500:
            raise RuntimeError(f"Gmail API temporarily unavailable (HTTP {resp.status_code})")
        if resp.status_code >= 400:
            raise ValueError(f"Gmail API error (HTTP {resp.status_code})")
        if not resp.content:
            return {}
        try:
            data = resp.json()
        except (ValueError, RecursionError) as e:  # malformed or hostile (deeply nested) JSON
            raise ValueError("Gmail API returned an invalid response") from e
        if not isinstance(data, dict):
            raise ValueError("Gmail API returned an invalid response")
        return data

    @staticmethod
    def _check_id(message_id: str) -> str:
        if not _ID_RE.match(message_id or ""):
            raise ValueError(f"Invalid Gmail message ID '{message_id}'")
        return message_id

    async def search(self, query: str, max_results: int) -> list[dict[str, Any]]:
        max_results = max(1, min(max_results, 50))
        listing = await self._request("GET", "/users/me/messages", params={"q": query, "maxResults": max_results})
        out = []
        for ref in listing.get("messages", [])[:max_results]:
            msg = await self._request(
                "GET",
                f"/users/me/messages/{self._check_id(ref['id'])}",
                params={"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]},
            )
            h = _headers(msg.get("payload", {}))
            out.append({"id": msg["id"], "from": h.get("from", ""), "subject": h.get("subject", ""), "date": h.get("date", ""), "snippet": msg.get("snippet", "")})
        return out

    async def read(self, message_id: str) -> dict[str, Any]:
        msg = await self._request("GET", f"/users/me/messages/{self._check_id(message_id)}", params={"format": "full"})
        payload = msg.get("payload", {})
        h = _headers(payload)
        walk = _Walk()
        _walk_parts(payload, walk)
        plain, html = walk.plain, walk.html
        if walk.notes:
            plain = plain + walk.notes  # visible to the scanner and the model: never silent
        return {
            "id": msg["id"],
            "thread_id": msg.get("threadId", ""),
            "from": h.get("from", ""),
            "to": h.get("to", ""),
            "date": h.get("date", ""),
            "subject": h.get("subject", ""),
            "snippet": msg.get("snippet", ""),
            "body_plain": "\n".join(plain),
            "body_html": "\n".join(html),
        }

    @staticmethod
    def _raw_mime(to: str, subject: str, body: str) -> str:
        em = EmailMessage()
        em["To"] = to  # header injection (CR/LF) raises ValueError here
        em["Subject"] = subject
        em.set_content(body)
        return base64.urlsafe_b64encode(em.as_bytes()).decode("ascii")

    async def create_draft(self, to: str, subject: str, body: str) -> dict[str, Any]:
        res = await self._request("POST", "/users/me/drafts", json_body={"message": {"raw": self._raw_mime(to, subject, body)}})
        return mock_state.record_draft(to=to, subject=subject, body=body, draft_id=res["id"])

    async def _allowed_recipients(self) -> list[str]:
        configured = [e.strip().lower() for e in settings.GMAIL_SEND_ALLOWLIST.split(",") if e.strip()]
        if configured:
            return configured
        _, own = await get_access_token(self.user_id)  # default: only the connected account itself
        return [own.lower()] if own else []

    async def send(self, to: str, subject: str, body: str, draft_id: str | None) -> dict[str, Any]:
        if to.strip().lower() not in await self._allowed_recipients():
            raise ValueError(f"Recipient '{to}' not permitted by GMAIL_SEND_ALLOWLIST")
        if draft_id:
            res = await self._request("POST", "/users/me/drafts/send", json_body={"id": self._check_id(draft_id)})
        else:
            res = await self._request("POST", "/users/me/messages/send", json_body={"raw": self._raw_mime(to, subject, body)})
        return mock_state.record_sent_mail(to=to, subject=subject, body=body, draft_id=draft_id, message_id=res["id"])


def get_backend(user_id: str) -> GmailBackend:
    return RealGmailBackend(user_id) if settings.GMAIL_MODE == "real" else MockGmailBackend()

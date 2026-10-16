"""Shared fake Google (OAuth + Gmail REST) built from env/mock/mailbox.json for parity/OAuth tests."""

from __future__ import annotations

import base64
import json
from urllib.parse import parse_qs

import httpx

from app.tools.gmail_backend import load_mock_mailbox
from app.tools.htmltext import looks_like_html

SCOPES = "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.compose"


def b64(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")


def to_gmail_message(m: dict, fmt: str = "full", alternative_plain: str | None = None) -> dict:
    body = m.get("body", "")
    headers = [
        {"name": "From", "value": m.get("from", "")},
        {"name": "To", "value": m.get("to", "")},
        {"name": "Subject", "value": m.get("subject", "")},
        {"name": "Date", "value": m.get("date", "")},
    ]
    if looks_like_html(body):
        leaf = {"mimeType": "text/html", "body": {"data": b64(body)}}
        if alternative_plain is not None:
            payload = {"mimeType": "multipart/alternative", "headers": headers, "parts": [{"mimeType": "text/plain", "body": {"data": b64(alternative_plain)}}, leaf]}
        else:
            payload = {"mimeType": "multipart/mixed", "headers": headers, "parts": [leaf, {"mimeType": "application/pdf", "filename": "a.pdf", "body": {"attachmentId": "x"}}]}
    else:
        payload = {"mimeType": "text/plain", "headers": headers, "body": {"data": b64(body)}}
    if fmt == "metadata":
        payload = {"headers": headers}
    return {"id": m["id"], "threadId": m.get("thread_id", ""), "snippet": m.get("snippet", ""), "payload": payload}


class FakeGoogle:
    def __init__(self, *, email="owner@gmail.com", refresh_status=200, token_scope=SCOPES, refresh_token="1//refresh-secret", alt_plain=None):
        self.email = email
        self.refresh_status = refresh_status
        self.token_scope = token_scope
        self.refresh_token = refresh_token
        self.alt_plain = alt_plain
        self.calls: list[tuple[str, str]] = []
        self.sent: list[dict] = []
        self.drafts: list[dict] = []
        self.reject_next_api_call_with_401 = False
        self.transport = httpx.MockTransport(self.handle)

    def handle(self, req: httpx.Request) -> httpx.Response:
        url = req.url
        self.calls.append((req.method, url.path))
        if url.host == "oauth2.googleapis.com":
            form = {k: v[0] for k, v in parse_qs(req.content.decode()).items()}
            if form.get("grant_type") == "authorization_code":
                if form.get("code") != "good-code":
                    return httpx.Response(400, json={"error": "invalid_grant"})
                return httpx.Response(200, json={"access_token": "ya29.a", "expires_in": 3600, "refresh_token": self.refresh_token, "scope": self.token_scope})
            if self.refresh_status != 200:
                return httpx.Response(self.refresh_status, json={"error": "invalid_grant"})
            return httpx.Response(200, json={"access_token": "ya29.b", "expires_in": 3600})
        assert url.host == "gmail.googleapis.com", url
        if not req.headers.get("authorization", "").startswith("Bearer ya29."):
            return httpx.Response(401, json={"error": "unauth"})
        if self.reject_next_api_call_with_401:
            self.reject_next_api_call_with_401 = False
            return httpx.Response(401, json={"error": "expired"})
        path = url.path.removeprefix("/gmail/v1/users/me")
        mailbox = {m["id"]: m for m in load_mock_mailbox()}
        if path == "/profile":
            return httpx.Response(200, json={"emailAddress": self.email})
        if path == "/messages" and req.method == "GET":
            q = url.params.get("q", "").lower()
            ids = [m["id"] for m in mailbox.values() if q in f"{m.get('subject','')} {m.get('from','')} {m.get('snippet','')} {m.get('body','')}".lower() or q in [l.lower() for l in m.get("labels", [])]]
            return httpx.Response(200, json={"messages": [{"id": i} for i in ids[: int(url.params.get("maxResults", 10))]]})
        if path.startswith("/messages/") and path != "/messages/send" and req.method == "GET":
            mid = path.rsplit("/", 1)[1]
            if mid not in mailbox:
                return httpx.Response(404, json={})
            return httpx.Response(200, json=to_gmail_message(mailbox[mid], url.params.get("format", "full"), self.alt_plain))
        if path == "/drafts":
            self.drafts.append(json.loads(req.content))
            return httpx.Response(200, json={"id": f"r-draft-{len(self.drafts)}", "message": {"id": "m"}})
        if path == "/drafts/send":
            self.sent.append({"draft": json.loads(req.content)})
            return httpx.Response(200, json={"id": f"r-sent-{len(self.sent)}"})
        if path == "/messages/send":
            self.sent.append(json.loads(req.content))
            return httpx.Response(200, json={"id": f"r-sent-{len(self.sent)}"})
        return httpx.Response(404, json={})

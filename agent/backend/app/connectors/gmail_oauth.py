"""
Gmail OAuth2 connector integration (Google "Web application" client).

* Scopes are the minimum: gmail.readonly + gmail.compose. A token response carrying
  any other scope, or missing one of these, is rejected.
* The OAuth `state` is a short-lived signed JWT bound to the EVA user, so a forged or
  replayed callback cannot attach someone else's mailbox to a user.
* Refresh tokens are Fernet-encrypted at rest; plaintext tokens/access tokens are never
  logged and never leave this module except as an Authorization header to Google.
* If Google rejects the refresh token (Testing-mode tokens expire after ~7 days, or the
  user revoked access) the account is flagged and callers get ReconnectNeeded; the
  connectors API surfaces this as status "reconnect_needed".
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from cryptography.fernet import InvalidToken
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.connectors.encryption import decrypt_token, encrypt_token
from app.db.models import ConnectorAccount

logger = logging.getLogger(__name__)

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
]
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1"
STATE_TTL_SECONDS = 600
TESTING_EXPIRY_HINT = "Testing mode: refresh token expires in ~7 days"
STATUS_CONNECTED = "connected"
STATUS_RECONNECT_NEEDED = "reconnect_needed"


class ReconnectNeeded(RuntimeError):
    """The stored Google grant is missing, revoked or expired; the user must reconnect Gmail."""

    def __init__(self, message: str = "Gmail connection needs to be re-authorised (reconnect needed)") -> None:
        super().__init__(message)


class OAuthError(ValueError):
    pass


# --- HTTP transport (injectable for tests) -----------------------------------
_google_transport: httpx.AsyncBaseTransport | None = None
_access_cache: dict[str, tuple[str, float]] = {}


def set_google_transport(transport: httpx.AsyncBaseTransport | None) -> None:
    """Test hook: route all Google calls through a mock transport."""
    global _google_transport
    _google_transport = transport
    _access_cache.clear()


def google_client(timeout: float = 10.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, transport=_google_transport)


# --- state -------------------------------------------------------------------
def make_oauth_state(user_id: str) -> str:
    now = int(time.time())
    payload = {"sub": user_id, "purpose": "gmail_oauth", "nonce": uuid.uuid4().hex, "iat": now, "exp": now + STATE_TTL_SECONDS}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def verify_oauth_state(state: str) -> str:
    try:
        payload = jwt.decode(state, settings.JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError as e:
        raise OAuthError("Invalid or expired OAuth state") from e
    if payload.get("purpose") != "gmail_oauth" or not payload.get("sub"):
        raise OAuthError("Invalid OAuth state")
    return str(payload["sub"])


def get_gmail_auth_url(user_id: str) -> str:
    """Generate the Google OAuth authorization URL (offline access, forced consent for a refresh token)."""
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(GMAIL_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": make_oauth_state(user_id),
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


# --- callback ----------------------------------------------------------------
async def handle_gmail_oauth_callback(code: str, user_id: str, session: AsyncSession) -> dict[str, Any]:
    """Exchange the authorization code, verify scopes, store the encrypted refresh token."""
    data = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
    }
    async with google_client() as client:
        resp = await client.post(GOOGLE_TOKEN_URL, data=data)
        if resp.status_code != 200:
            # Do not echo the response body: it can contain request details.
            raise OAuthError(f"Google rejected the authorization code (HTTP {resp.status_code})")
        token_data = resp.json()

        granted = set((token_data.get("scope") or "").split())
        if granted:
            if not set(GMAIL_SCOPES) <= granted:
                raise OAuthError("Required Gmail scopes (readonly + compose) were not granted")
            extra = granted - set(GMAIL_SCOPES)
            if extra:
                raise OAuthError("Refusing token with scopes beyond gmail.readonly + gmail.compose")

        refresh_token = token_data.get("refresh_token", "")
        if not refresh_token:
            raise OAuthError("Google did not return a refresh token; revoke access and reconnect")

        email = None
        access = token_data.get("access_token")
        if access:
            try:
                prof = await client.get(f"{GMAIL_API_BASE}/users/me/profile", headers={"Authorization": f"Bearer {access}"})
                if prof.status_code == 200:
                    email = prof.json().get("emailAddress")
            except httpx.HTTPError:
                logger.warning("gmail profile lookup failed during OAuth callback")

    await session.execute(delete(ConnectorAccount).where(ConnectorAccount.user_id == user_id, ConnectorAccount.provider == "gmail"))
    session.add(
        ConnectorAccount(
            user_id=user_id,
            provider="gmail",
            account_email=email,
            encrypted_refresh_token=encrypt_token(refresh_token),
            scopes=" ".join(GMAIL_SCOPES),
            expires_hint=TESTING_EXPIRY_HINT,
            status=STATUS_CONNECTED,
        )
    )
    await session.commit()
    _access_cache.pop(user_id, None)
    return {"status": "connected", "provider": "gmail", "account": email}


# --- runtime token use -------------------------------------------------------
async def _load_account(session: AsyncSession, user_id: str) -> ConnectorAccount | None:
    res = await session.execute(select(ConnectorAccount).where(ConnectorAccount.user_id == user_id, ConnectorAccount.provider == "gmail"))
    return res.scalar_one_or_none()


def account_needs_reconnect(acc: ConnectorAccount | None) -> bool:
    return acc is not None and acc.status == STATUS_RECONNECT_NEEDED


async def mark_reconnect_needed(session: AsyncSession, acc: ConnectorAccount, reason: str) -> None:
    acc.status = STATUS_RECONNECT_NEEDED
    acc.expires_hint = reason[:128]
    await session.commit()
    _access_cache.pop(acc.user_id, None)


async def get_access_token(user_id: str, session: AsyncSession | None = None) -> tuple[str, str | None]:
    """Return (access_token, account_email). Raises ReconnectNeeded when no valid grant exists."""
    if session is None:
        from app.db.database import async_session_factory

        async with async_session_factory() as s:
            return await get_access_token(user_id, s)

    acc = await _load_account(session, user_id)
    if acc is None:
        raise ReconnectNeeded("Gmail is not connected for this user")
    if account_needs_reconnect(acc):
        raise ReconnectNeeded()

    cached = _access_cache.get(user_id)
    if cached and cached[1] > time.time() + 30:
        return cached[0], acc.account_email

    try:
        refresh = decrypt_token(acc.encrypted_refresh_token)
    except (InvalidToken, ValueError):
        await mark_reconnect_needed(session, acc, "stored token unreadable")
        raise ReconnectNeeded() from None

    try:
        async with google_client() as client:
            resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "refresh_token": refresh,
                    "grant_type": "refresh_token",
                },
            )
    except httpx.HTTPError as e:
        # Transient network failure: NOT a revoked grant, so the account is not flagged.
        raise RuntimeError(f"Google token endpoint unreachable ({type(e).__name__})") from e
    if resp.status_code in (400, 401):
        await mark_reconnect_needed(session, acc, "Google rejected the refresh token")
        raise ReconnectNeeded()
    if resp.status_code != 200:
        raise RuntimeError(f"Google token endpoint error (HTTP {resp.status_code})")
    body = resp.json()
    token = body["access_token"]
    _access_cache[user_id] = (token, time.time() + int(body.get("expires_in", 3600)))
    return token, acc.account_email


def invalidate_access_token(user_id: str) -> None:
    _access_cache.pop(user_id, None)

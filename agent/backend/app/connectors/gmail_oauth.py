"""
Gmail OAuth2 connector integration.
Handles Google Cloud OAuth Web Application flow with minimum required scopes:
gmail.readonly and gmail.compose.
"""

from __future__ import annotations

import logging
from urllib.parse import urlencode
from typing import Any
import httpx
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


def get_gmail_auth_url(user_id: str) -> str:
    """Generate Google OAuth authorization URL."""
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(GMAIL_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": user_id,
    }
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"


async def handle_gmail_oauth_callback(code: str, user_id: str, session: AsyncSession) -> dict[str, Any]:
    """Exchange authorization code for refresh token and save encrypted token."""
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(token_url, data=data)
        if resp.status_code != 200:
            raise ValueError(f"Failed to exchange Google OAuth code: {resp.text}")
        token_data = resp.json()

    refresh_token = token_data.get("refresh_token", "")
    encrypted = encrypt_token(refresh_token)

    # Clean existing and create account entry
    del_stmt = delete(ConnectorAccount).where(ConnectorAccount.user_id == user_id, ConnectorAccount.provider == "gmail")
    await session.execute(del_stmt)

    acc = ConnectorAccount(
        user_id=user_id,
        provider="gmail",
        account_email="connected-user@gmail.com",
        encrypted_refresh_token=encrypted,
        scopes=" ".join(GMAIL_SCOPES),
        expires_hint="Testing mode: expires in ~7 days",
    )
    session.add(acc)
    await session.commit()
    return {"status": "connected", "provider": "gmail"}

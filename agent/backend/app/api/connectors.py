"""
Connectors API endpoints for managing external integrations (Gmail OAuth).
"""

from __future__ import annotations

from typing import Annotated, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.config import settings
from app.connectors.gmail_oauth import get_gmail_auth_url, handle_gmail_oauth_callback
from app.db.database import get_db_session
from app.db.models import ConnectorAccount, User

router = APIRouter(tags=["connectors"])


@router.get("/api/connectors")
async def list_connectors(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[dict[str, Any]]:
    stmt = select(ConnectorAccount).where(
        ConnectorAccount.user_id == current_user.id,
        ConnectorAccount.provider == "gmail",
    )
    result = await session.execute(stmt)
    acc = result.scalar_one_or_none()

    if settings.GMAIL_MODE == "mock":
        gmail_info = {
            "id": "gmail",
            "name": "Gmail Connector",
            "status": "connected",
            "mode": "mock",
            "account": "user@eva.local",
            "scopes": ["gmail.readonly", "gmail.compose"],
            "expires_hint": "Mock sandbox: active",
        }
    elif acc:
        gmail_info = {
            "id": "gmail",
            "name": "Gmail Connector",
            "status": "connected",
            "mode": "real",
            "account": acc.account_email,
            "scopes": acc.scopes.split(),
            "expires_hint": acc.expires_hint or "Testing mode: expires in ~7 days",
        }
    else:
        gmail_info = {
            "id": "gmail",
            "name": "Gmail Connector",
            "status": "disconnected",
            "mode": "real",
            "account": None,
            "scopes": [],
            "expires_hint": "Connect via Google OAuth",
        }

    return [gmail_info]


@router.get("/api/connectors/gmail/auth-url")
async def get_auth_url(
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, str]:
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GOOGLE_CLIENT_ID not configured in backend environment",
        )
    return {"url": get_gmail_auth_url(current_user.id)}


@router.get("/oauth/gmail/callback")
async def gmail_oauth_callback(
    code: str,
    state: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Any:
    try:
        await handle_gmail_oauth_callback(code, user_id=state, session=session)
        # Redirect to frontend connectors page if running in browser
        return {"status": "success", "message": "Gmail account successfully connected"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth callback failed: {e}",
        )


@router.delete("/api/connectors/gmail")
async def disconnect_gmail(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, str]:
    del_stmt = delete(ConnectorAccount).where(
        ConnectorAccount.user_id == current_user.id,
        ConnectorAccount.provider == "gmail",
    )
    await session.execute(del_stmt)
    await session.commit()
    return {"status": "disconnected", "provider": "gmail"}

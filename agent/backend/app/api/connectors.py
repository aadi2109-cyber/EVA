"""
Connectors API endpoints for managing external integrations (Gmail OAuth).
"""

from __future__ import annotations

from typing import Annotated, Any
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.config import settings
from app.connectors.gmail_oauth import (
    OAuthError,
    TESTING_EXPIRY_HINT,
    account_needs_reconnect,
    get_gmail_auth_url,
    handle_gmail_oauth_callback,
    invalidate_access_token,
    verify_oauth_state,
)
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
        reconnect = account_needs_reconnect(acc)
        gmail_info = {
            "id": "gmail",
            "name": "Gmail Connector",
            "status": "reconnect_needed" if reconnect else "connected",
            "mode": "real",
            "account": acc.account_email,
            "scopes": acc.scopes.split(),
            "expires_hint": "Google access expired or was revoked - reconnect Gmail" if reconnect else (acc.expires_hint or TESTING_EXPIRY_HINT),
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

    from app.connectors.telegram import telegram_connector
    telegram_info = await telegram_connector.get_status(current_user.id, session)

    return [gmail_info, telegram_info]


@router.post("/api/connectors/telegram/link-code")
async def generate_telegram_link_code(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, Any]:
    """Generate a single-use verification code to link a Telegram private chat."""
    from app.connectors.telegram import telegram_connector
    return await telegram_connector.generate_link_code(current_user.id, session)


@router.post("/api/connectors/telegram/verify")
async def verify_telegram_link(
    data: dict[str, Any],
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, Any]:
    """
    Verify and link a chat manually or via simulated mock update.
    Requires: code, chat_id, and chat_type.
    """
    from app.connectors.telegram import telegram_connector
    code = data.get("code", "")
    chat_id = str(data.get("chat_id", ""))
    chat_type = data.get("chat_type", "private")
    chat_username = data.get("chat_username")
    try:
        return await telegram_connector.verify_and_link_chat(
            code=code,
            chat_id=chat_id,
            chat_type=chat_type,
            chat_username=chat_username,
            session=session,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/api/connectors/telegram")
async def disconnect_telegram(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, str]:
    from app.connectors.telegram import telegram_connector
    await telegram_connector.unlink_account(current_user.id, session)
    return {"status": "disconnected", "provider": "telegram"}


@router.post("/api/connectors/telegram/webhook")
async def telegram_webhook(
    update: dict[str, Any],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_telegram_bot_api_secret_token: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """
    Inbound Telegram webhook.
    Validates X-Telegram-Bot-Api-Secret-Token if configured.
    Processes link commands (e.g. /start EVA-XXXXXX) or normal messages.
    """
    if settings.TELEGRAM_WEBHOOK_SECRET:
        if x_telegram_bot_api_secret_token != settings.TELEGRAM_WEBHOOK_SECRET:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid webhook secret")

    from app.connectors.telegram import telegram_connector
    update_id = update.get("update_id", 0)
    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return {"ok": True, "skipped": "no_message"}

    chat = msg.get("chat", {})
    chat_id = str(chat.get("id", ""))
    chat_type = chat.get("type", "")
    text = (msg.get("text") or "").strip()
    sender = msg.get("from", {}).get("username") or str(msg.get("from", {}).get("id", "user"))

    # Check for linking code command: "/start EVA-XXXX" or "EVA-XXXX"
    if text.startswith("/start "):
        potential_code = text.split("/start ", 1)[1].strip()
    else:
        potential_code = text.strip()

    if potential_code.startswith("EVA-") and len(potential_code) == 10:
        try:
            res = await telegram_connector.verify_and_link_chat(
                code=potential_code,
                chat_id=chat_id,
                chat_type=chat_type,
                chat_username=chat.get("username"),
                session=session,
            )
            return {"ok": True, "action": "linked", "result": res}
        except ValueError as e:
            logger.warning("Telegram linking failed for chat %s: %s", chat_id, e)
            return {"ok": False, "error": str(e)}

    # Normal incoming message -> deduplicate and record into mock state/message store
    is_new = telegram_connector.record_inbound_update(update_id, chat_id, text, sender=sender)
    return {"ok": True, "action": "recorded" if is_new else "duplicate"}


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
    state: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    code: str | None = None,
    error: str | None = None,
) -> Any:
    try:
        user_id = verify_oauth_state(state)  # signed, short-lived, bound to the EVA user
        if error or not code:
            raise OAuthError("Google authorization was not granted")
        await handle_gmail_oauth_callback(code, user_id=user_id, session=session)
        return {"status": "success", "message": "Gmail account successfully connected"}
    except OAuthError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"OAuth callback failed: {e}")
    except Exception:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="OAuth callback failed: could not reach Google")


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
    invalidate_access_token(current_user.id)
    return {"status": "disconnected", "provider": "gmail"}

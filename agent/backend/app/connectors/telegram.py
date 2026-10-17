"""
Telegram connector integration.
Handles private chat linking via short-lived single-use verification codes,
mock mode for evaluation, and real mode using Telegram's official Bot API.
Never logs or leaks bot token.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.connectors.encryption import decrypt_token, encrypt_token
from app.db.models import ConnectorAccount, TelegramLinkCode
from env.mock.state import state as mock_state

logger = logging.getLogger(__name__)

CODE_TTL_MINUTES = 10
TELEGRAM_API_BASE = "https://api.telegram.org"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TelegramConnector:
    """
    Telegram connector adapter supporting user chat linking and message dispatch.
    """

    def __init__(self, mode: str | None = None) -> None:
        self.mode = mode or settings.TELEGRAM_MODE
        self._processed_update_ids: set[int] = set()

    async def get_status(self, user_id: str, session: AsyncSession) -> dict[str, Any]:
        """Return connector status for an authenticated EVA user."""
        stmt = select(ConnectorAccount).where(
            ConnectorAccount.user_id == user_id,
            ConnectorAccount.provider == "telegram",
        )
        res = await session.execute(stmt)
        acc = res.scalar_one_or_none()

        if self.mode == "mock":
            return {
                "id": "telegram",
                "name": "Telegram Connector",
                "status": "connected" if acc or True else "disconnected",
                "mode": "mock",
                "account": acc.account_identifier if acc else "@eva_mock_bot",
                "scopes": ["messages:read", "messages:write"],
                "expires_hint": "Mock sandbox: active",
            }

        if acc:
            return {
                "id": "telegram",
                "name": "Telegram Connector",
                "status": acc.status or "connected",
                "mode": "real",
                "account": acc.account_identifier or "Linked Chat",
                "scopes": acc.scopes.split() if acc.scopes else ["messages:read", "messages:write"],
                "expires_hint": acc.expires_hint or "Linked private chat active",
            }

        return {
            "id": "telegram",
            "name": "Telegram Connector",
            "status": "disconnected",
            "mode": "real",
            "account": None,
            "scopes": [],
            "expires_hint": "Link your Telegram account using a verification code",
        }

    async def generate_link_code(self, user_id: str, session: AsyncSession) -> dict[str, Any]:
        """
        Generate a cryptographically secure, short-lived single-use verification code.
        Format: EVA-XXXXXX
        """
        code_str = f"EVA-{secrets.token_hex(3).upper()}"
        expires_at = utc_now() + timedelta(minutes=CODE_TTL_MINUTES)

        link_code = TelegramLinkCode(
            code=code_str,
            user_id=user_id,
            expires_at=expires_at,
            used=False,
        )
        session.add(link_code)
        await session.commit()

        bot_name = "@eva_mock_bot" if self.mode == "mock" else "your configured EVA Telegram bot"
        instructions = f"Send this code directly to {bot_name} on Telegram: {code_str}"

        return {
            "code": code_str,
            "expires_at": expires_at.isoformat(),
            "instructions": instructions,
        }

    async def verify_and_link_chat(
        self,
        code: str,
        chat_id: str,
        chat_type: str,
        chat_username: str | None,
        session: AsyncSession,
    ) -> dict[str, Any]:
        """
        Verify single-use code from an incoming message and link private chat to user.
        Strictly rejects non-private chats (no groups/channels).
        """
        if chat_type != "private":
            raise ValueError("Only private chats may be linked to an EVA user account.")

        stmt = select(TelegramLinkCode).where(
            TelegramLinkCode.code == code.strip(),
            TelegramLinkCode.used == False,  # noqa: E712
        )
        res = await session.execute(stmt)
        record = res.scalar_one_or_none()

        if not record:
            raise ValueError("Invalid or already used verification code.")

        now = utc_now()
        exp = record.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < now:
            raise ValueError("Verification code has expired. Please generate a new code in EVA.")

        # Mark code as consumed
        record.used = True

        # Check existing connection for user
        user_stmt = select(ConnectorAccount).where(
            ConnectorAccount.user_id == record.user_id,
            ConnectorAccount.provider == "telegram",
        )
        user_res = await session.execute(user_stmt)
        acc = user_res.scalar_one_or_none()

        identifier = f"chat:{chat_id}" + (f" (@{chat_username})" if chat_username else "")
        encrypted_token = encrypt_token(str(chat_id))

        if acc:
            acc.account_identifier = identifier
            acc.encrypted_refresh_token = encrypted_token
            acc.status = "connected"
            acc.scopes = "messages:read messages:write"
        else:
            acc = ConnectorAccount(
                user_id=record.user_id,
                provider="telegram",
                account_identifier=identifier,
                encrypted_refresh_token=encrypted_token,
                scopes="messages:read messages:write",
                status="connected",
            )
            session.add(acc)

        await session.commit()
        return {
            "status": "linked",
            "user_id": record.user_id,
            "chat_id": chat_id,
            "account_identifier": identifier,
        }

    async def unlink_account(self, user_id: str, session: AsyncSession) -> None:
        """Disconnect Telegram and delete stored credentials."""
        stmt = select(ConnectorAccount).where(
            ConnectorAccount.user_id == user_id,
            ConnectorAccount.provider == "telegram",
        )
        res = await session.execute(stmt)
        acc = res.scalar_one_or_none()
        if acc:
            await session.delete(acc)
            await session.commit()

    async def get_history(self, chat_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """
        Fetch inbound/outbound Telegram messages for chat_id.
        In mock mode, reads from mock state.
        In real mode, returns stored recent messages for this chat.
        """
        obs = mock_state.observe_state()
        all_tg_msgs = obs.get("mock_telegram_messages", [])
        chat_msgs = [m for m in all_tg_msgs if str(m.get("chat_id")) == str(chat_id)]
        return chat_msgs[-limit:]

    async def send_message(self, chat_id: str, text: str) -> dict[str, Any]:
        """
        Send a message via Telegram adapter.
        In mock mode, saves to mock state.
        In real mode, dispatches to Telegram Bot API sendMessage.
        """
        if self.mode == "real":
            bot_token = settings.TELEGRAM_BOT_TOKEN
            if not bot_token:
                raise ValueError("TELEGRAM_BOT_TOKEN is not configured.")

            url = f"{TELEGRAM_API_BASE}/bot{bot_token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": text,
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code != 200:
                    raise RuntimeError(f"Telegram API send failed: HTTP {resp.status_code}")
                data = resp.json()
                if not data.get("ok"):
                    raise RuntimeError(f"Telegram API error: {data.get('description', 'Unknown error')}")

            msg_id = str(data.get("result", {}).get("message_id", "tg-live"))
            return {"status": "sent", "message_id": msg_id, "chat_id": str(chat_id)}

        # Mock mode
        obs = mock_state.observe_state()
        sent = obs.get("mock_telegram_sent", [])
        msg_record = {
            "id": f"tg-msg-{len(sent) + 1}",
            "chat_id": str(chat_id),
            "text": text,
        }
        sent.append(msg_record)
        mock_state.set_custom_state("mock_telegram_sent", sent)

        all_tg_msgs = obs.get("mock_telegram_messages", [])
        all_tg_msgs.append({
            "id": msg_record["id"],
            "chat_id": str(chat_id),
            "sender": "bot",
            "text": text,
        })
        mock_state.set_custom_state("mock_telegram_messages", all_tg_msgs)

        return {"status": "sent", "message_id": msg_record["id"], "chat_id": str(chat_id)}

    def record_inbound_update(self, update_id: int, chat_id: str, text: str, sender: str = "user") -> bool:
        """
        Deduplicates update_id and stores incoming message in observable state.
        Returns False if update_id was already processed (duplicate).
        """
        if update_id in self._processed_update_ids:
            logger.warning("Duplicate Telegram update %s ignored", update_id)
            return False

        self._processed_update_ids.add(update_id)

        obs = mock_state.observe_state()
        all_tg_msgs = obs.get("mock_telegram_messages", [])
        all_tg_msgs.append({
            "id": f"update-{update_id}",
            "chat_id": str(chat_id),
            "sender": sender,
            "text": text,
        })
        mock_state.set_custom_state("mock_telegram_messages", all_tg_msgs)
        return True


# Default singleton
telegram_connector = TelegramConnector()

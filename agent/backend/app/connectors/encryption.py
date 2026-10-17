"""
Fernet symmetric encryption for OAuth tokens stored at rest.
Ensures tokens never leak into logs, SSE streams, or model context.
"""

from __future__ import annotations

import base64
from cryptography.fernet import Fernet
from app.config import settings


def _get_fernet() -> Fernet:
    key = settings.TOKEN_ENC_KEY
    if settings.APP_ENV == "prod":
        # Production requires a real Fernet key (Fernet.generate_key()); no silent fallbacks.
        if not key:
            raise ValueError("TOKEN_ENC_KEY must be set when APP_ENV=prod")
        return Fernet(key.encode("utf-8"))
    if not key:
        # Default dev key (32 url-safe base64 bytes)
        key = "dGhpc2lzYTMyeS1ieXRlcy1mZXJuZXQta2V5LTEyMzQ1Njc="

    # Ensure key is valid 32-byte base64
    try:
        raw_bytes = base64.urlsafe_b64decode(key.encode("utf-8"))
        if len(raw_bytes) != 32:
            # Pad or slice to 32 bytes
            raw_bytes = (raw_bytes + b"0" * 32)[:32]
            key = base64.urlsafe_b64encode(raw_bytes).decode("utf-8")
        return Fernet(key.encode("utf-8"))
    except Exception:
        # Fallback to deterministic valid 32-byte key
        valid_bytes = b"eva_agent_secret_encryption_key!"
        safe_key = base64.urlsafe_b64encode(valid_bytes)
        return Fernet(safe_key)


def encrypt_token(token: str) -> str:
    if not token:
        return ""
    f = _get_fernet()
    return f.encrypt(token.encode("utf-8")).decode("utf-8")


def decrypt_token(encrypted_token: str) -> str:
    if not encrypted_token:
        return ""
    f = _get_fernet()
    return f.decrypt(encrypted_token.encode("utf-8")).decode("utf-8")

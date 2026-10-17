"""
Tests for Connectors and Token Encryption.
"""

import pytest
from app.connectors.encryption import decrypt_token, encrypt_token


def test_token_encryption_roundtrip():
    raw_refresh_token = "1//04_secret_google_refresh_token_abcdef123456"
    encrypted = encrypt_token(raw_refresh_token)

    # Must be encrypted and not equal to plaintext
    assert encrypted != raw_refresh_token
    assert raw_refresh_token not in encrypted

    # Decryption must match original
    decrypted = decrypt_token(encrypted)
    assert decrypted == raw_refresh_token


@pytest.mark.asyncio
async def test_connectors_list_mock_mode(async_client):
    login_res = await async_client.post(
        "/api/auth/login",
        json={"email": "user@eva.local", "password": "UserPassword123!"},
    )
    token = login_res.json()["access_token"]

    res = await async_client.get(
        "/api/connectors",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    connectors = res.json()
    assert len(connectors) >= 1
    gmail_conn = next(c for c in connectors if c["id"] == "gmail")
    assert gmail_conn["status"] == "connected"
    assert gmail_conn["mode"] == "mock"

    tg_conn = next(c for c in connectors if c["id"] == "telegram")
    assert tg_conn["status"] == "connected"
    assert tg_conn["mode"] == "mock"
    assert tg_conn["account"] == "@eva_mock_bot"

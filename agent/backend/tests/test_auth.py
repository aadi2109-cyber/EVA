"""
Tests for Authentication, Password Hashing, JWT Tokens, and Authorization.
"""

import pytest
from app.auth.security import create_access_token, decode_access_token, hash_password, verify_password
from app.config import settings


def test_password_hashing():
    pw = "SuperSecretPassword123!"
    hashed = hash_password(pw)
    assert hashed != pw
    assert verify_password(pw, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


def test_jwt_token_roundtrip():
    payload = {"sub": "user-123", "email": "test@eva.local", "role": "user"}
    token = create_access_token(payload)
    decoded = decode_access_token(token)
    assert decoded["sub"] == "user-123"
    assert decoded["email"] == "test@eva.local"
    assert decoded["role"] == "user"


@pytest.mark.asyncio
async def test_api_login_success(async_client):
    res = await async_client.post(
        "/api/auth/login",
        json={"email": settings.SEED_USER_EMAIL, "password": settings.SEED_USER_PASSWORD},
    )
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["user"]["email"] == settings.SEED_USER_EMAIL
    assert data["user"]["role"] == "user"


@pytest.mark.asyncio
async def test_api_login_invalid_password(async_client):
    res = await async_client.post(
        "/api/auth/login",
        json={"email": settings.SEED_USER_EMAIL, "password": "WrongPassword!"},
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_api_me_authenticated(async_client):
    login_res = await async_client.post(
        "/api/auth/login",
        json={"email": settings.SEED_ADMIN_EMAIL, "password": settings.SEED_ADMIN_PASSWORD},
    )
    token = login_res.json()["access_token"]

    me_res = await async_client.get(
        "/api/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_res.status_code == 200
    assert me_res.json()["role"] == "admin"

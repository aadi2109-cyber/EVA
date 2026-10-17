"""MiniMoth OTP integration tests. All upstream responses are mocked."""

from __future__ import annotations

import httpx
import pytest

from app.auth.minimoth import MinimothClient, MinimothError, normalize_indian_phone
from app.auth.security import decode_access_token
from app.config import settings
from app.db.database import async_session_factory
from app.db.models import User
from sqlalchemy import select

REAL_ASYNC_CLIENT = httpx.AsyncClient


def install_mock_client(monkeypatch, handler):
    class MockAsyncClient:
        def __init__(self, **kwargs):
            kwargs.pop("transport", None)
            self.client = REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler), **kwargs)

        async def __aenter__(self):
            return await self.client.__aenter__()

        async def __aexit__(self, *args):
            return await self.client.__aexit__(*args)

    monkeypatch.setattr("app.auth.minimoth.httpx.AsyncClient", MockAsyncClient)


def test_phone_normalization():
    assert normalize_indian_phone("9876543210") == "+919876543210"
    assert normalize_indian_phone("+919876543210") == "+919876543210"
    for value in ("5876543210", "+441234567890", "+91987654321", "９８７６５４３２１０"):
        with pytest.raises(ValueError):
            normalize_indian_phone(value)


@pytest.mark.asyncio
async def test_minimoth_client_sends_expected_headers_and_payload(monkeypatch):
    monkeypatch.setattr(settings, "MINIMOTH_API_KEY", "test-key")
    seen = {}

    async def handler(request: httpx.Request):
        seen["headers"] = request.headers
        seen["body"] = request.content
        return httpx.Response(200, json={"otp_id": "otp_test_1"})

    install_mock_client(monkeypatch, handler)
    client = MinimothClient()
    result = await client.send_otp("+919876543210")
    assert result == "otp_test_1"
    assert seen["headers"]["x-api-key"] == "test-key"
    assert seen["headers"]["content-type"] == "application/json"
    assert seen["body"] == b'{"phone":"+919876543210"}'


@pytest.mark.asyncio
async def test_minimoth_delivery_status_is_normalized_and_proxied(async_client, monkeypatch):
    monkeypatch.setattr(settings, "MINIMOTH_API_KEY", "test-key")
    seen = {}

    async def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("x-api-key")
        return httpx.Response(200, json={"otp_id": "otp_test_9", "status": "delivered", "channel": "whatsapp"})

    install_mock_client(monkeypatch, handler)
    response = await async_client.get("/api/auth/otp/status/otp_test_9")
    assert response.status_code == 200
    assert response.json() == {"status": "delivered", "channel": "whatsapp"}
    assert seen["url"].endswith("/v1/otp/status/otp_test_9")
    assert seen["key"] == "test-key"


@pytest.mark.asyncio
async def test_minimoth_delivery_status_does_not_forward_unknown_fields_or_errors(monkeypatch):
    monkeypatch.setattr(settings, "MINIMOTH_API_KEY", "test-key")

    async def queued(request: httpx.Request):
        return httpx.Response(200, json={"status": "queued", "phone": "+919876543210", "debug": "secret"})

    install_mock_client(monkeypatch, queued)
    assert await MinimothClient().otp_status("otp-safe") == {"status": "queued", "channel": None}

    async def provider_failure(request: httpx.Request):
        return httpx.Response(404, json={"code": "OTP_REQUEST_NOT_FOUND", "error": "private details"})

    install_mock_client(monkeypatch, provider_failure)
    with pytest.raises(MinimothError) as error:
        await MinimothClient().otp_status("otp-safe")
    assert error.value.http_status == 404
    assert "private details" not in error.value.public_message


@pytest.mark.asyncio
async def test_otp_flow_creates_reuses_user_and_issues_eva_jwt(async_client, monkeypatch):
    monkeypatch.setattr(settings, "MINIMOTH_API_KEY", "test-key")
    async def send(self, phone):
        return "otp_test_2"

    async def verify(self, phone, code):
        assert phone == "+919876543210"
        assert code == "001234"
        return None

    monkeypatch.setattr(MinimothClient, "send_otp", send)
    monkeypatch.setattr(MinimothClient, "verify_otp", verify)
    sent = await async_client.post("/api/auth/otp/send", json={"phone": "9876543210"})
    assert sent.status_code == 200
    assert sent.json() == {"message": "OTP request accepted; delivery status may still be pending.", "otp_id": "otp_test_2"}

    login = await async_client.post("/api/auth/otp/verify", json={"phone": "+919876543210", "code": "001234"})
    assert login.status_code == 200
    body = login.json()
    assert "refresh_token" not in body
    assert "access_token" in body
    claims = decode_access_token(body["access_token"])
    assert claims["sub"] == body["user"]["id"]
    assert body["user"]["phone"] == "+919876543210"

    login_again = await async_client.post("/api/auth/otp/verify", json={"phone": "9876543210", "code": "001234"})
    assert login_again.status_code == 200
    assert login_again.json()["user"]["id"] == body["user"]["id"]
    async with async_session_factory() as session:
        user = (await session.execute(select(User).where(User.phone == "+919876543210"))).scalar_one()
        assert user.email is None and user.hashed_password is None


@pytest.mark.asyncio
async def test_invalid_phone_and_code_rejected_before_upstream(async_client, monkeypatch):
    async def should_not_call(*args, **kwargs):
        raise AssertionError("provider should not be called")

    monkeypatch.setattr(MinimothClient, "verify_otp", should_not_call)
    assert (await async_client.post("/api/auth/otp/verify", json={"phone": "123", "code": "123456"})).status_code == 422
    assert (await async_client.post("/api/auth/otp/verify", json={"phone": "9876543210", "code": 123456})).status_code == 422
    invalid_code = await async_client.post(
        "/api/auth/otp/verify", json={"phone": "9876543210", "code": "private-otp-value"}
    )
    assert invalid_code.status_code == 422
    assert "private-otp-value" not in invalid_code.text
    assert "9876543210" not in invalid_code.text


@pytest.mark.asyncio
async def test_missing_minimoth_key_returns_safe_service_error(async_client, monkeypatch):
    monkeypatch.setattr(settings, "MINIMOTH_API_KEY", "")
    response = await async_client.post("/api/auth/otp/send", json={"phone": "9876543210"})
    assert response.status_code == 503
    assert "temporarily unavailable" in response.json()["detail"]
    assert "API key" not in response.text


@pytest.mark.asyncio
async def test_test_key_is_rejected_with_clear_real_delivery_guidance(async_client, monkeypatch):
    monkeypatch.setattr(settings, "MINIMOTH_API_KEY", "mm_test_example")
    response = await async_client.post("/api/auth/otp/send", json={"phone": "9876543210"})
    assert response.status_code == 503
    assert "test key" in response.json()["detail"]
    assert "live project key" in response.json()["detail"]


@pytest.mark.asyncio
async def test_invalid_expired_and_limited_provider_errors_are_safe(monkeypatch):
    async def handler(request: httpx.Request):
        return httpx.Response(400, json={"code": "INVALID_OTP", "error": "do not expose upstream text"})

    monkeypatch.setattr(settings, "MINIMOTH_API_KEY", "test-key")
    # Build client with a mocked AsyncClient context.
    install_mock_client(monkeypatch, handler)
    with pytest.raises(MinimothError) as error:
        await MinimothClient().verify_otp("+919876543210", "123456")
    assert error.value.http_status == 401
    assert "do not expose" not in error.value.public_message

    async def limited(request: httpx.Request):
        return httpx.Response(429, json={"code": "VERIFY_RATE_LIMITED"})

    install_mock_client(monkeypatch, limited)
    with pytest.raises(MinimothError) as error:
        await MinimothClient().verify_otp("+919876543210", "123456")
    assert error.value.http_status == 429


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("upstream_status", "code", "expected_status"),
    [
        (400, "OTP_NOT_FOUND", 401),  # expired or already consumed
        (429, "OTP_RATE_LIMITED", 429),
        (429, "VERIFY_RATE_LIMITED", 429),
        (500, "SMS_FAILED", 503),
        (503, "unrecognized", 503),
    ],
)
async def test_minimoth_failure_codes_are_mapped_without_upstream_text(
    monkeypatch, upstream_status, code, expected_status
):
    monkeypatch.setattr(settings, "MINIMOTH_API_KEY", "test-key")

    async def handler(request: httpx.Request):
        return httpx.Response(upstream_status, json={"code": code, "error": "sensitive upstream detail"})

    install_mock_client(monkeypatch, handler)
    with pytest.raises(MinimothError) as error:
        await MinimothClient().verify_otp("+919876543210", "123456")
    assert error.value.http_status == expected_status
    assert "sensitive upstream detail" not in error.value.public_message


@pytest.mark.asyncio
async def test_unrecognized_provider_429_is_still_a_safe_rate_limit(monkeypatch):
    monkeypatch.setattr(settings, "MINIMOTH_API_KEY", "test-key")

    async def handler(request: httpx.Request):
        return httpx.Response(429, json={"code": "NEW_PROVIDER_CODE", "error": "private detail"})

    install_mock_client(monkeypatch, handler)
    with pytest.raises(MinimothError) as error:
        await MinimothClient().send_otp("+919876543210")
    assert error.value.http_status == 429
    assert "private detail" not in error.value.public_message


@pytest.mark.asyncio
async def test_minimoth_timeout_and_invalid_success_payload_fail_closed(monkeypatch):
    monkeypatch.setattr(settings, "MINIMOTH_API_KEY", "test-key")

    async def timeout(request: httpx.Request):
        raise httpx.ReadTimeout("request timed out", request=request)

    install_mock_client(monkeypatch, timeout)
    with pytest.raises(MinimothError) as error:
        await MinimothClient().verify_otp("+919876543210", "123456")
    assert error.value.http_status == 503

    async def malformed_success(request: httpx.Request):
        return httpx.Response(200, json={"valid": False})

    install_mock_client(monkeypatch, malformed_success)
    with pytest.raises(MinimothError) as error:
        await MinimothClient().verify_otp("+919876543210", "123456")
    assert error.value.http_status == 503


def test_production_configuration_requires_random_jwt_https_origins_and_minimoth_key():
    from app.config import Settings

    with pytest.raises(ValueError, match="JWT_SECRET"):
        Settings(APP_ENV="dev", JWT_SECRET="", _env_file=None)
    with pytest.raises(ValueError, match="HTTPS FRONTEND_ORIGINS"):
        Settings(
            APP_ENV="prod",
            JWT_SECRET="a" * 48,
            FRONTEND_ORIGINS="*",
            MINIMOTH_API_KEY="test-key",
            _env_file=None,
        )
    with pytest.raises(ValueError, match="MINIMOTH_API_KEY"):
        Settings(
            APP_ENV="prod",
            JWT_SECRET="a" * 48,
            FRONTEND_ORIGINS="https://eva.example",
            MINIMOTH_API_KEY="",
            _env_file=None,
        )


@pytest.mark.asyncio
async def test_logout_requires_authentication_and_me_stays_protected(async_client, monkeypatch):
    assert (await async_client.post("/api/auth/logout")).status_code == 401
    assert (await async_client.get("/api/me")).status_code == 401

    from app.config import settings

    login = await async_client.post(
        "/api/auth/login",
        json={"email": settings.SEED_USER_EMAIL, "password": settings.SEED_USER_PASSWORD},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert (await async_client.post("/api/auth/logout", headers=headers)).status_code == 200
    assert (await async_client.get("/api/me", headers=headers)).status_code == 401

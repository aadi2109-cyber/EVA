"""Gmail OAuth: auth-url, signed state, callback, scope enforcement, Fernet storage, reconnect state."""

from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from sqlalchemy import select

from app.config import settings
from app.connectors.encryption import decrypt_token
from app.connectors.gmail_oauth import GMAIL_SCOPES, OAuthError, make_oauth_state, set_google_transport, verify_oauth_state
from app.db.database import async_session_factory
from app.db.models import ConnectorAccount

from gmail_fakes import FakeGoogle


@pytest.fixture(autouse=True)
def _cfg(monkeypatch):
    monkeypatch.setattr(settings, "GMAIL_MODE", "real")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "cid.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "csecret")
    yield
    set_google_transport(None)


async def _login(client, email="user@eva.local", pw="UserPassword123!"):
    r = await client.post("/api/auth/login", json={"email": email, "password": pw})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _start(client, hdr):
    r = await client.get("/api/connectors/gmail/auth-url", headers=hdr)
    assert r.status_code == 200
    url = urlparse(r.json()["url"])
    return url, {k: v[0] for k, v in parse_qs(url.query).items()}


async def test_auth_url_minimal_scopes_and_offline(async_client):
    hdr = await _login(async_client)
    url, q = await _start(async_client, hdr)
    assert url.netloc == "accounts.google.com"
    assert q["scope"].split() == GMAIL_SCOPES  # readonly + compose, nothing broader
    assert q["access_type"] == "offline" and q["client_id"].startswith("cid")
    assert q["redirect_uri"] == settings.GOOGLE_REDIRECT_URI


async def test_auth_url_requires_login_and_config(async_client, monkeypatch):
    assert (await async_client.get("/api/connectors/gmail/auth-url")).status_code in (401, 403)
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "")
    hdr = await _login(async_client)
    assert (await async_client.get("/api/connectors/gmail/auth-url", headers=hdr)).status_code == 400


async def test_callback_roundtrip_encrypts_refresh_token(async_client):
    hdr = await _login(async_client)
    _, q = await _start(async_client, hdr)
    fake = FakeGoogle(email="me@gmail.com")
    set_google_transport(fake.transport)
    r = await async_client.get("/oauth/gmail/callback", params={"code": "good-code", "state": q["state"]})
    assert r.status_code == 200, r.text
    assert "1//refresh-secret" not in r.text

    async with async_session_factory() as s:
        acc = (await s.execute(select(ConnectorAccount))).scalar_one()
    assert acc.account_email == "me@gmail.com"
    assert acc.encrypted_refresh_token != "1//refresh-secret" and "refresh-secret" not in acc.encrypted_refresh_token
    assert decrypt_token(acc.encrypted_refresh_token) == "1//refresh-secret"
    assert acc.scopes.split() == GMAIL_SCOPES

    lst = (await async_client.get("/api/connectors", headers=hdr)).json()[0]
    assert lst["status"] == "connected" and lst["mode"] == "real" and lst["account"] == "me@gmail.com"
    assert "refresh" not in str(lst).lower().replace("refresh token expires", "")


async def test_callback_rejects_forged_expired_and_replayed_state(async_client):
    set_google_transport(FakeGoogle().transport)
    # forged: raw user id as state (old, vulnerable behaviour)
    r = await async_client.get("/oauth/gmail/callback", params={"code": "good-code", "state": "some-user-id"})
    assert r.status_code == 400
    # signed with the wrong key
    bad = jwt.encode({"sub": "u", "purpose": "gmail_oauth", "exp": 9999999999}, "wrong-key-wrong-key-wrong-key-wrong-key", algorithm="HS256")
    assert (await async_client.get("/oauth/gmail/callback", params={"code": "good-code", "state": bad})).status_code == 400
    # expired
    old = jwt.encode({"sub": "u", "purpose": "gmail_oauth", "exp": 1}, settings.JWT_SECRET, algorithm="HS256")
    assert (await async_client.get("/oauth/gmail/callback", params={"code": "good-code", "state": old})).status_code == 400
    # a normal access token must not be accepted as OAuth state
    hdr = await _login(async_client)
    access = hdr["Authorization"].split()[1]
    assert (await async_client.get("/oauth/gmail/callback", params={"code": "good-code", "state": access})).status_code == 400
    async with async_session_factory() as s:
        assert (await s.execute(select(ConnectorAccount))).first() is None


async def test_callback_user_denied_or_bad_code(async_client):
    hdr = await _login(async_client)
    _, q = await _start(async_client, hdr)
    set_google_transport(FakeGoogle().transport)
    assert (await async_client.get("/oauth/gmail/callback", params={"error": "access_denied", "state": q["state"]})).status_code == 400
    assert (await async_client.get("/oauth/gmail/callback", params={"code": "bad", "state": q["state"]})).status_code == 400


@pytest.mark.parametrize("scope", [
    GMAIL_SCOPES[0],  # compose missing
    " ".join(GMAIL_SCOPES + ["https://mail.google.com/"]),  # broader than allowed
])
async def test_callback_rejects_wrong_scopes(async_client, scope):
    hdr = await _login(async_client)
    _, q = await _start(async_client, hdr)
    set_google_transport(FakeGoogle(token_scope=scope).transport)
    r = await async_client.get("/oauth/gmail/callback", params={"code": "good-code", "state": q["state"]})
    assert r.status_code == 400
    async with async_session_factory() as s:
        assert (await s.execute(select(ConnectorAccount))).first() is None


async def test_callback_requires_refresh_token(async_client):
    hdr = await _login(async_client)
    _, q = await _start(async_client, hdr)
    set_google_transport(FakeGoogle(refresh_token="").transport)
    assert (await async_client.get("/oauth/gmail/callback", params={"code": "good-code", "state": q["state"]})).status_code == 400


async def test_connectors_list_reconnect_needed_and_disconnect(async_client, monkeypatch):
    from app.connectors.gmail_oauth import mark_reconnect_needed
    hdr = await _login(async_client)
    _, q = await _start(async_client, hdr)
    set_google_transport(FakeGoogle().transport)
    await async_client.get("/oauth/gmail/callback", params={"code": "good-code", "state": q["state"]})
    async with async_session_factory() as s:
        acc = (await s.execute(select(ConnectorAccount))).scalar_one()
        await mark_reconnect_needed(s, acc, "test")
    item = (await async_client.get("/api/connectors", headers=hdr)).json()[0]
    assert item["status"] == "reconnect_needed" and "reconnect" in item["expires_hint"].lower()
    assert (await async_client.delete("/api/connectors/gmail", headers=hdr)).status_code == 200
    assert (await async_client.get("/api/connectors", headers=hdr)).json()[0]["status"] == "disconnected"


def test_state_roundtrip_and_tamper():
    s = make_oauth_state("user-1")
    assert verify_oauth_state(s) == "user-1"
    with pytest.raises(OAuthError):
        verify_oauth_state(s[:-2] + "xx")


def test_prod_requires_valid_fernet_key(monkeypatch):
    from cryptography.fernet import Fernet
    from app.connectors.encryption import decrypt_token, encrypt_token
    monkeypatch.setattr(settings, "APP_ENV", "prod")
    monkeypatch.setattr(settings, "TOKEN_ENC_KEY", "")
    with pytest.raises(ValueError):
        encrypt_token("t")
    monkeypatch.setattr(settings, "TOKEN_ENC_KEY", Fernet.generate_key().decode())
    assert decrypt_token(encrypt_token("t")) == "t"

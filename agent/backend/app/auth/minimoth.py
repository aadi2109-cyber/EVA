"""Small HTTP client for MiniMoth's OTP-only REST API."""

from __future__ import annotations

import time
import hashlib
from collections import deque
from threading import Lock

import httpx

from app.config import settings

TIMEOUT = httpx.Timeout(5.0, connect=2.0)
_rate_lock = Lock()
_send_attempts: dict[str, deque[float]] = {}
_verify_attempts: dict[str, deque[float]] = {}
_MAX_RATE_LIMIT_KEYS = 10_000


def enforce_local_rate_limit(phone: str, *, verify: bool) -> None:
    """Best-effort per-process limit; production multi-worker deployments need a shared limiter."""
    now = time.monotonic()
    window = 600
    # Stay within MiniMoth's documented limit of 3 sends / 10 minutes per phone.
    limit = 3 if not verify else 10
    buckets = _verify_attempts if verify else _send_attempts
    key = hashlib.sha256(phone.encode("utf-8")).hexdigest()
    with _rate_lock:
        for tracked in (_send_attempts, _verify_attempts):
            for tracked_key, attempts in list(tracked.items()):
                while attempts and now - attempts[0] >= window:
                    attempts.popleft()
                if not attempts:
                    tracked.pop(tracked_key, None)
        bucket = buckets.get(key)
        if bucket is None:
            if len(buckets) >= _MAX_RATE_LIMIT_KEYS:
                raise MinimothError(429, "Too many attempts; wait before trying again")
            bucket = deque()
            buckets[key] = bucket
        while bucket and now - bucket[0] >= window:
            bucket.popleft()
        if len(bucket) >= limit:
            raise MinimothError(429, "Too many attempts; wait before trying again")
        bucket.append(now)


def normalize_indian_phone(value: str) -> str:
    """Accept +91 plus ten digits or ten digits beginning 6-9; return E.164 form."""
    if not isinstance(value, str):
        raise ValueError("Invalid Indian phone number")
    if value.startswith("+"):
        if len(value) != 13 or not value.startswith("+91"):
            raise ValueError("Invalid Indian phone number")
        digits = value[3:]
    else:
        if value.startswith("91") and len(value) == 12:
            raise ValueError("Invalid Indian phone number")
        digits = value
    if len(digits) != 10 or not digits.isascii() or not digits.isdigit() or digits[0] not in "6789":
        raise ValueError("Invalid Indian phone number")
    return f"+91{digits}"


class MinimothError(Exception):
    def __init__(self, http_status: int, public_message: str):
        self.http_status = http_status
        self.public_message = public_message
        super().__init__(public_message)


class MinimothClient:
    def __init__(self) -> None:
        if not settings.MINIMOTH_API_KEY:
            raise MinimothError(503, "Phone verification is temporarily unavailable")
        if settings.MINIMOTH_API_KEY.strip().startswith("mm_test_"):
            raise MinimothError(
                503,
                "MiniMoth is configured with a test key, which does not send real OTPs. Configure a live project key to enable phone login.",
            )
        self.base_url = settings.MINIMOTH_BASE_URL.rstrip("/")

    async def _post(self, endpoint: str, payload: dict[str, str]) -> dict:
        headers = {
            "X-Api-Key": settings.MINIMOTH_API_KEY,
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.post(f"{self.base_url}{endpoint}", json=payload, headers=headers)
        except httpx.TimeoutException:
            raise MinimothError(503, "Phone verification service timed out; try again") from None
        except httpx.HTTPError:
            raise MinimothError(503, "Phone verification service is unavailable; try again") from None

        try:
            data = response.json()
        except ValueError:
            data = {}
        if response.is_success:
            return data if isinstance(data, dict) else {}

        code = data.get("code") if isinstance(data, dict) else None
        # Normalize status/code combinations; never forward untrusted provider text.
        if response.status_code == 429:
            raise MinimothError(429, "Too many attempts; wait before trying again")
        if code in {"INVALID_OTP", "OTP_NOT_FOUND", "INVALID_OTP_CODE"}:
            raise MinimothError(401, "Invalid or expired verification code")
        if code in {"OTP_RATE_LIMITED", "VERIFY_RATE_LIMITED", "RATE_LIMITED"}:
            raise MinimothError(429, "Too many verification attempts; wait before trying again")
        if code in {"INVALID_PHONE"}:
            raise MinimothError(422, "Enter a valid Indian mobile number")
        if code in {"INVALID_API_KEY", "MISSING_API_KEY"}:
            raise MinimothError(503, "Phone verification is temporarily unavailable")
        if code in {"SMS_FAILED", "INSUFFICIENT_BALANCE"}:
            raise MinimothError(503, "Phone verification could not deliver a code right now")
        raise MinimothError(503, "Phone verification service is unavailable; try again")

    async def send_otp(self, phone: str) -> str | None:
        result = await self._post("/v1/otp/send", {"phone": phone})
        otp_id = result.get("otp_id")
        return otp_id if isinstance(otp_id, str) and len(otp_id) <= 128 else None

    async def otp_status(self, otp_id: str) -> dict[str, str | None]:
        headers = {"X-Api-Key": settings.MINIMOTH_API_KEY}
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.get(f"{self.base_url}/v1/otp/status/{otp_id}", headers=headers)
        except httpx.TimeoutException:
            raise MinimothError(503, "Phone verification service timed out; try again") from None
        except httpx.HTTPError:
            raise MinimothError(503, "Phone verification service is unavailable; try again") from None

        try:
            result = response.json()
        except ValueError:
            result = {}
        if not response.is_success:
            code = result.get("code") if isinstance(result, dict) else None
            if response.status_code == 429:
                raise MinimothError(429, "Too many attempts; wait before trying again")
            if code == "OTP_REQUEST_NOT_FOUND":
                raise MinimothError(404, "Delivery status is not available for this request")
            if code in {"INVALID_API_KEY", "MISSING_API_KEY"}:
                raise MinimothError(503, "Phone verification is temporarily unavailable")
            raise MinimothError(503, "Phone verification service is unavailable; try again")

        state = result.get("status") if isinstance(result, dict) else None
        channel = result.get("channel") if isinstance(result, dict) else None
        if state not in {"queued", "delivered", "failed"}:
            raise MinimothError(503, "Phone verification returned an invalid delivery status")
        if channel not in {"whatsapp", "sms"}:
            channel = None
        return {"status": state, "channel": channel}

    async def verify_otp(self, phone: str, code: str) -> None:
        # MiniMoth confirms verification with a successful response containing access_token.
        # Tokens from MiniMoth are intentionally discarded; EVA mints its own JWT afterward.
        result = await self._post("/v1/otp/verify", {"phone": phone, "code": code})
        if not isinstance(result.get("access_token"), str) or not result["access_token"]:
            raise MinimothError(503, "Phone verification service returned an invalid response")

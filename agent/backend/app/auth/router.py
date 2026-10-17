"""
Authentication API routes: login and current user profile.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.auth.minimoth import MinimothClient, MinimothError, enforce_local_rate_limit, normalize_indian_phone
from app.auth.security import create_access_token, decode_access_token, fingerprint_access_token, verify_password
from app.db.database import get_db_session
from app.db.models import RevokedToken, User

router = APIRouter(prefix="/api", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: str
    email: str | None
    phone: str | None = None
    role: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class PhoneRequest(BaseModel):
    phone: str = Field(..., min_length=10, max_length=16)

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str) -> str:
        try:
            return normalize_indian_phone(value)
        except ValueError as exc:
            raise ValueError("Enter a valid Indian mobile number") from exc


class VerifyOTPRequest(PhoneRequest):
    code: str = Field(..., pattern=r"^\d{6}$")


class OTPSendResponse(BaseModel):
    message: str
    otp_id: str | None = None


class OTPStatusResponse(BaseModel):
    status: str
    channel: str | None = None


class AuthenticatedUserResponse(BaseModel):
    id: str
    email: str | None
    phone: str | None = None
    role: str


class OTPLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AuthenticatedUserResponse


@router.post("/auth/login", response_model=LoginResponse)
async def login(
    req: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> LoginResponse:
    stmt = select(User).where(User.email == req.email)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or user.hashed_password is None or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    token = create_access_token(data={"sub": user.id, "email": user.email, "role": user.role})
    return LoginResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse(id=user.id, email=user.email, phone=user.phone, role=user.role),
    )


@router.post("/auth/otp/send", response_model=OTPSendResponse)
async def send_phone_otp(req: PhoneRequest) -> OTPSendResponse:
    try:
        enforce_local_rate_limit(req.phone, verify=False)
        client = MinimothClient()
        otp_id = await client.send_otp(req.phone)
    except MinimothError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.public_message) from None
    return OTPSendResponse(message="OTP request accepted; delivery status may still be pending.", otp_id=otp_id)


@router.get("/auth/otp/status/{otp_id}", response_model=OTPStatusResponse)
async def phone_otp_status(
    otp_id: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,128}$")],
) -> OTPStatusResponse:
    try:
        result = await MinimothClient().otp_status(otp_id)
    except MinimothError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.public_message) from None
    return OTPStatusResponse(**result)


@router.post("/auth/otp/verify", response_model=OTPLoginResponse)
async def verify_phone_otp(
    req: VerifyOTPRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> OTPLoginResponse:
    try:
        enforce_local_rate_limit(req.phone, verify=True)
        client = MinimothClient()
        await client.verify_otp(req.phone, req.code)
    except MinimothError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.public_message) from None

    result = await session.execute(select(User).where(User.phone == req.phone))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(phone=req.phone, email=None, hashed_password=None, role="user")
        session.add(user)
        try:
            await session.commit()
        except Exception:
            await session.rollback()
            # Concurrent successful verification may have created this phone already.
            result = await session.execute(select(User).where(User.phone == req.phone))
            user = result.scalar_one_or_none()
            if user is None:
                raise HTTPException(status_code=409, detail="Could not create the account") from None
        if user is not None:
            await session.refresh(user)

    token = create_access_token(data={"sub": user.id, "email": user.email, "role": user.role})
    return OTPLoginResponse(
        access_token=token,
        user=AuthenticatedUserResponse(id=user.id, email=user.email, phone=user.phone, role=user.role),
    )


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        phone=current_user.phone,
        role=current_user.role,
    )


@router.post("/auth/logout")
async def logout(
    current_user: Annotated[User, Depends(get_current_user)],
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, str]:
    credentials = request.headers.get("authorization", "")
    token = credentials[7:].strip() if credentials.lower().startswith("bearer ") else ""
    try:
        payload = decode_access_token(token)
        expiry = datetime.fromtimestamp(float(payload["exp"]), tz=timezone.utc)
    except (ValueError, KeyError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid or expired authentication credentials") from None
    session.add(RevokedToken(token_hash=fingerprint_access_token(token), expires_at=expiry))
    await session.commit()
    await session.execute(delete(RevokedToken).where(RevokedToken.expires_at <= datetime.now(timezone.utc)))
    await session.commit()
    return {"status": "logged_out"}

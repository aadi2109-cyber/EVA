"""
Health check endpoint reporting status of agent backend and connected guard.
"""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter

from app.config import settings
from app.guard_client.factory import get_guard_client

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("")
async def health_check() -> dict[str, Any]:
    guard = get_guard_client()
    try:
        guard_health = await guard.health()
        guard_data = guard_health.model_dump(mode="json")
    except Exception as e:
        guard_data = {
            "status": "down",
            "tier2_available": False,
            "t3_available": False,
            "align_available": False,
            "contract_version": "0.1.0",
            "kill_switch": {"all_write_tools": False, "tools": []},
            "error": str(e),
        }

    backend_data = {
        "status": "ok",
        "app_env": settings.APP_ENV,
        "guard_transport": settings.GUARD_TRANSPORT,
        "gmail_mode": settings.GMAIL_MODE,
        "guard_profile": settings.GUARD_PROFILE,
    }

    return {
        "backend": backend_data,
        "guard": guard_data,
    }

"""
Factory for GuardClient instance based on configuration.
"""

from __future__ import annotations

from app.config import settings
from app.guard_client.base import GuardClient
from app.guard_client.http import HttpGuardClient
from app.guard_client.in_process import InProcessGuardClient

_guard_client_instance: GuardClient | None = None


def get_guard_client() -> GuardClient:
    global _guard_client_instance
    if _guard_client_instance is not None:
        return _guard_client_instance

    if settings.GUARD_TRANSPORT == "http":
        _guard_client_instance = HttpGuardClient()
    else:
        _guard_client_instance = InProcessGuardClient()

    return _guard_client_instance


def set_guard_client(client: GuardClient | None) -> None:
    """Override the active guard client (for tests)."""
    global _guard_client_instance
    _guard_client_instance = client

"""Auth package for EVA Agent Backend."""

from app.auth.deps import get_current_user, require_admin
from app.auth.router import router as auth_router
from app.auth.security import create_access_token, decode_access_token, hash_password, verify_password
from app.auth.seeder import seed_users

__all__ = [
    "get_current_user",
    "require_admin",
    "auth_router",
    "create_access_token",
    "decode_access_token",
    "hash_password",
    "verify_password",
    "seed_users",
]

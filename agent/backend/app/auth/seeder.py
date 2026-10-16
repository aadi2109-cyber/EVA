"""
Database seeder for default admin and user accounts.
"""

from __future__ import annotations

import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import hash_password
from app.config import settings
from app.db.database import async_session_factory
from app.db.models import User

logger = logging.getLogger(__name__)


async def seed_users() -> None:
    async with async_session_factory() as session:
        # Check admin
        admin_stmt = select(User).where(User.email == settings.SEED_ADMIN_EMAIL)
        res = await session.execute(admin_stmt)
        if not res.scalar_one_or_none():
            admin = User(
                email=settings.SEED_ADMIN_EMAIL,
                hashed_password=hash_password(settings.SEED_ADMIN_PASSWORD),
                role="admin",
            )
            session.add(admin)
            logger.info("Seeded initial admin account: %s", settings.SEED_ADMIN_EMAIL)

        # Check standard user
        user_stmt = select(User).where(User.email == settings.SEED_USER_EMAIL)
        res = await session.execute(user_stmt)
        if not res.scalar_one_or_none():
            user = User(
                email=settings.SEED_USER_EMAIL,
                hashed_password=hash_password(settings.SEED_USER_PASSWORD),
                role="user",
            )
            session.add(user)
            logger.info("Seeded initial user account: %s", settings.SEED_USER_EMAIL)

        await session.commit()

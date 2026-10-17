"""
Pytest configuration and fixtures for EVA Agent Backend.
"""

from __future__ import annotations

import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path
import pytest
from httpx import ASGITransport, AsyncClient

# Set APP_ENV=dev for testing
os.environ["APP_ENV"] = "dev"
os.environ["GUARD_TRANSPORT"] = "inprocess"
os.environ["JWT_SECRET"] = "test-only-random-looking-secret-for-eva-auth-tests-2026"
# Per-process database so concurrent pytest runs never share (and corrupt) one SQLite file.
_TEST_DB_DIR = tempfile.mkdtemp(prefix="eva-test-db-")
atexit.register(shutil.rmtree, _TEST_DB_DIR, ignore_errors=True)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_DB_DIR}/test_agent.db"

# Ensure imports resolve
ROOT_DIR = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "agent" / "backend"))
sys.path.insert(0, str(ROOT_DIR / "contracts"))
sys.path.insert(0, str(ROOT_DIR / "guard"))

from app.auth.seeder import seed_users
from app.db.database import Base, engine, init_db
from app.guard_client.factory import set_guard_client
from app.guard_client.in_process import InProcessGuardClient
from app.main import app
from eva_guard.stub import StubGuard


@pytest.fixture(autouse=True)
async def setup_test_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await seed_users()
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def stub_guard_client():
    stub = StubGuard()
    client = InProcessGuardClient(guard_instance=stub)
    set_guard_client(client)
    yield client
    set_guard_client(None)


@pytest.fixture
async def async_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

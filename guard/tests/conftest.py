"""Tests must not share durable guard state: each test gets its own SQLite file via GUARD_DB_PATH."""
import os
import tempfile

import pytest

# Import-time default (service.main builds a Guard on import).
os.environ.setdefault("GUARD_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="guard-test-"), "session.db"))


@pytest.fixture(autouse=True)
def _isolated_guard_db(tmp_path, monkeypatch):
    monkeypatch.setenv("GUARD_DB_PATH", str(tmp_path / "guard.db"))

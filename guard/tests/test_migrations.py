import sqlite3
import subprocess
import sys
from pathlib import Path

from eva_guard.api import Guard
from eval.store import EvalStore

GUARD_DIR = Path(__file__).resolve().parents[1]


def _alembic(db, *args):
    import os
    env = {**os.environ, "GUARD_DB_PATH": str(db)}
    return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=GUARD_DIR, env=env, capture_output=True, text=True)


def _schema(db):
    c = sqlite3.connect(db)
    try:
        return {t: [(r[1], r[2], r[3], r[5]) for r in c.execute(f"PRAGMA table_info({t})")]
                for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name!='alembic_version'")}
    finally:
        c.close()


def test_migrated_schema_matches_runtime_schema(tmp_path):
    runtime = tmp_path / "runtime.db"
    g = Guard(db_url=f"sqlite:///{runtime}"); EvalStore(runtime)
    migrated = tmp_path / "migrated.db"
    r = _alembic(migrated, "upgrade", "head")
    assert r.returncode == 0, r.stderr
    assert _schema(migrated) == _schema(runtime)


def test_upgrade_on_existing_runtime_db_is_safe_and_idempotent(tmp_path):
    db = tmp_path / "g.db"
    g = Guard(db_url=f"sqlite:///{db}")
    g._audit.log_event(task_id="t", event_type="x", actor="a", payload={})
    assert _alembic(db, "upgrade", "head").returncode == 0
    assert _alembic(db, "upgrade", "head").returncode == 0
    assert g._audit.verify_chain().valid and g._audit.verify_chain().chain_length == 1
    cur = _alembic(db, "current")
    assert "0001" in cur.stdout + cur.stderr


def test_baseline_downgrade_refused(tmp_path):
    db = tmp_path / "d.db"
    assert _alembic(db, "upgrade", "head").returncode == 0
    assert _alembic(db, "downgrade", "base").returncode != 0

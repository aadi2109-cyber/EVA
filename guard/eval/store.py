"""
eval_runs store (doc 01/04): every evaluation run is persisted with config, versions, hardware, seed and
failed traces so the admin Eval page reads real history rather than files. SQLite, same DB file as the
audit log by default (separate table; never touches the audit hash chain).
"""
from __future__ import annotations

import json
import os
import platform
import sqlite3
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from contracts.models import CONTRACT_VERSION

KINDS = ("scenarios", "drills", "align", "det")
_DDL = """
CREATE TABLE IF NOT EXISTS eval_runs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    created_at TEXT NOT NULL,
    git_sha TEXT,
    contract_version TEXT NOT NULL,
    config_json TEXT NOT NULL,
    versions_json TEXT NOT NULL,
    hardware TEXT NOT NULL,
    seed INTEGER,
    n INTEGER NOT NULL,
    summary_json TEXT NOT NULL,
    failures_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_eval_runs_kind_ts ON eval_runs(kind, created_at);
"""


def default_db_path() -> Path:
    return Path(os.getenv("GUARD_DB_PATH", str(Path(__file__).resolve().parents[1] / "guard.db")))


def _git_sha() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=3).stdout.strip() or None
    except Exception:  # noqa: BLE001
        return None


def hardware() -> str:
    return f"{platform.machine()} {platform.system()} {os.cpu_count()} cpu, python {platform.python_version()}"


class EvalStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(_DDL)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(str(self.db_path))
        c.row_factory = sqlite3.Row
        return c

    def save_run(self, kind: str, summary: dict[str, Any], n: int, failures: list[Any] | None = None,
                 config: dict[str, Any] | None = None, versions: dict[str, Any] | None = None,
                 seed: int | None = None) -> str:
        if kind not in KINDS:
            raise ValueError(f"unknown eval kind {kind!r}")
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        versions = {"contract": CONTRACT_VERSION, **(versions or {})}
        with self._conn() as c:
            c.execute(
                "INSERT INTO eval_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, kind, datetime.now(timezone.utc).isoformat(), _git_sha(), CONTRACT_VERSION,
                 json.dumps(config or {}, default=str), json.dumps(versions, default=str), hardware(), seed, n,
                 json.dumps(summary, default=str), json.dumps(failures or [], default=str)),
            )
        return run_id

    @staticmethod
    def _row(r: sqlite3.Row, full: bool) -> dict[str, Any]:
        d = {"id": r["id"], "kind": r["kind"], "created_at": r["created_at"], "git_sha": r["git_sha"],
             "contract_version": r["contract_version"], "hardware": r["hardware"], "seed": r["seed"], "n": r["n"],
             "summary": json.loads(r["summary_json"]), "failed_count": len(json.loads(r["failures_json"]))}
        if full:
            d.update(config=json.loads(r["config_json"]), versions=json.loads(r["versions_json"]),
                     failures=json.loads(r["failures_json"]))
        return d

    def list_runs(self, kind: str | None = None, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        q, p = "SELECT * FROM eval_runs", []
        if kind:
            q += " WHERE kind=?"; p.append(kind)
        q += " ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?"
        with self._conn() as c:
            return [self._row(r, False) for r in c.execute(q, (*p, limit, offset))]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM eval_runs WHERE id=?", (run_id,)).fetchone()
        return self._row(r, True) if r else None

    def latest(self, kind: str) -> dict[str, Any] | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM eval_runs WHERE kind=? ORDER BY created_at DESC, rowid DESC LIMIT 1", (kind,)).fetchone()
        return self._row(r, True) if r else None

    def summary(self) -> dict[str, Any]:
        """Admin Eval page payload: latest run per kind + Baseline/Basic/Full table + honest-claims footer."""
        latest = {k: self.latest(k) for k in KINDS}
        sc = latest["scenarios"]
        table = None
        if sc:
            s = sc["summary"]["profiles"]
            table = [{"metric": m, **{PROFILE_KEY[p]: s[p].get(m) for p in ("off", "basic", "full")}} for m in METRICS]
        return {
            "latest": {k: (None if v is None else {x: v[x] for x in ("id", "created_at", "git_sha", "n", "hardware", "seed", "summary", "failed_count")}) for k, v in latest.items()},
            "comparison_table": table,
            "notes": ["Every number is from a finite authored suite on the mock environment; zero successes is not immunity.",
                      "Detection recall is reported separately (kind=det); the gateway, not detection, carries the safety guarantee."],
        }


PROFILE_KEY = {"off": "baseline", "basic": "basic", "full": "full"}
METRICS = ["unauthorized_side_effects", "task_under_attack_completion", "clean_task_completion", "expectations_met"]

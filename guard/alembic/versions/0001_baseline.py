"""baseline: audit, authority state, config, eval runs

Revision ID: 0001
Revises:
Frozen copy of the schema the runtime creates with CREATE TABLE IF NOT EXISTS, so an existing DB can be
adopted (`alembic stamp 0001`) or a new one created (`alembic upgrade head`) with identical results.
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS audit_events (
        id TEXT PRIMARY KEY, ts TEXT NOT NULL, task_id TEXT NOT NULL, type TEXT NOT NULL, actor TEXT NOT NULL,
        payload_json TEXT NOT NULL, config_version INTEGER NOT NULL, model_versions TEXT NOT NULL,
        prev_hash TEXT NOT NULL, hash TEXT NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS idx_audit_task ON audit_events(task_id)",
    "CREATE INDEX IF NOT EXISTS idx_audit_type ON audit_events(type)",
    "CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_events(ts)",
    """CREATE TABLE IF NOT EXISTS task_policies (
        task_id TEXT PRIMARY KEY, policy_json TEXT NOT NULL, user_request TEXT NOT NULL, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS approvals (
        approval_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, approval_json TEXT NOT NULL, action_hash TEXT NOT NULL,
        approved INTEGER NOT NULL DEFAULT 0, consumed INTEGER NOT NULL DEFAULT 0, user_id TEXT,
        created_at TEXT NOT NULL, expires_at TEXT NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS idx_approvals_task ON approvals(task_id)",
    """CREATE TABLE IF NOT EXISTS config_versions (
        version INTEGER PRIMARY KEY, config_json TEXT NOT NULL, changed_by TEXT, approved_by TEXT,
        proposal_id TEXT, created_at TEXT NOT NULL)""",
    "CREATE TABLE IF NOT EXISTS config_proposals (proposal_id TEXT PRIMARY KEY, proposal_json TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS review_items (id TEXT PRIMARY KEY, item_json TEXT NOT NULL)",
    """CREATE TABLE IF NOT EXISTS kill_switch (
        id INTEGER PRIMARY KEY CHECK (id = 1), state_json TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS eval_runs (
        id TEXT PRIMARY KEY, kind TEXT NOT NULL, created_at TEXT NOT NULL, git_sha TEXT, contract_version TEXT NOT NULL,
        config_json TEXT NOT NULL, versions_json TEXT NOT NULL, hardware TEXT NOT NULL, seed INTEGER, n INTEGER NOT NULL,
        summary_json TEXT NOT NULL, failures_json TEXT NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS idx_eval_runs_kind_ts ON eval_runs(kind, created_at)",
]


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    # Never drop the audit log or authority state automatically.
    raise RuntimeError("Baseline downgrade is intentionally unsupported (would destroy audit/authority data)")

"""Initial database schema for EVA Agent Backend.

Revision ID: 001_initial
Revises: 
Create Date: 2026-10-15 22:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Users
    op.create_table(
        "users",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), nullable=False, server_default="user"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # Tasks
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("request", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="running"),
        sa.Column("policy_json", sqlite.JSON, nullable=True),
        sa.Column("final_text", sa.Text(), nullable=True),
        sa.Column("summary_json", sqlite.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tasks_user_id", "tasks", ["user_id"])

    # Messages
    op.create_table(
        "messages",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("task_id", sa.String(64), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_messages_task_id", "messages", ["task_id"])

    # Task events
    op.create_table(
        "task_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("task_id", sa.String(64), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("payload_json", sqlite.JSON, nullable=False),
        sa.UniqueConstraint("task_id", "seq", name="uq_task_events_task_seq"),
    )
    op.create_index("ix_task_events_task_id", "task_events", ["task_id"])
    op.create_index("idx_task_events_seq", "task_events", ["task_id", "seq"])

    # Tool executions
    op.create_table(
        "tool_executions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("task_id", sa.String(64), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("call_id", sa.String(64), nullable=False),
        sa.Column("tool_name", sa.String(64), nullable=False),
        sa.Column("args_json", sqlite.JSON, nullable=False),
        sa.Column("result_json", sqlite.JSON, nullable=True),
        sa.Column("raw_result_json", sqlite.JSON, nullable=True),
        sa.Column("disposition", sa.String(32), nullable=True),
        sa.Column("duration_ms", sa.Float(), server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tool_executions_task_id", "tool_executions", ["task_id"])

    # Connector accounts
    op.create_table(
        "connector_accounts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False, server_default="gmail"),
        sa.Column("account_email", sa.String(255), nullable=True),
        sa.Column("encrypted_refresh_token", sa.Text(), nullable=False),
        sa.Column("scopes", sa.String(512), nullable=False),
        sa.Column("expires_hint", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_connector_accounts_user_id", "connector_accounts", ["user_id"])

    # Approvals index
    op.create_table(
        "approvals_index",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("task_id", sa.String(64), nullable=False),
        sa.Column("call_id", sa.String(64), nullable=False),
        sa.Column("tool", sa.String(64), nullable=False),
        sa.Column("exact_action_json", sqlite.JSON, nullable=False),
        sa.Column("action_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_approvals_index_task_id", "approvals_index", ["task_id"])


def downgrade() -> None:
    op.drop_table("approvals_index")
    op.drop_table("connector_accounts")
    op.drop_table("tool_executions")
    op.drop_table("task_events")
    op.drop_table("messages")
    op.drop_table("tasks")
    op.drop_table("users")

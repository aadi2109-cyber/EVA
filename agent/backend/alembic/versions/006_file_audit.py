"""Add file_audit_events (audit trail for user file uploads).

Revision ID: 006_file_audit
Revises: 005_merge_otp_telegram
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "006_file_audit"
down_revision: Union[str, None] = "005_merge_otp_telegram"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "file_audit_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("path", sa.String(512), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_file_audit_events_user_id", "file_audit_events", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_file_audit_events_user_id", table_name="file_audit_events")
    op.drop_table("file_audit_events")

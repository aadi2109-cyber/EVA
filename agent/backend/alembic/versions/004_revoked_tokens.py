"""Persist EVA JWT revocations across backend workers.

Revision ID: 004_revoked_tokens
Revises: 003_user_phone_auth
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004_revoked_tokens"
down_revision: Union[str, None] = "003_user_phone_auth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "revoked_tokens",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_revoked_tokens_expires_at", "revoked_tokens", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_revoked_tokens_expires_at", table_name="revoked_tokens")
    op.drop_table("revoked_tokens")

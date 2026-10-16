"""Add telegram support: connector_accounts.account_identifier and telegram_link_codes table.

Revision ID: 003_telegram_connector
Revises: 002_connector_status
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "003_telegram_connector"
down_revision: Union[str, None] = "002_connector_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("connector_accounts") as batch:
        batch.add_column(sa.Column("account_identifier", sa.String(255), nullable=True))

    op.create_table(
        "telegram_link_codes",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("code", sa.String(32), unique=True, index=True, nullable=False),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_telegram_link_codes_user_id", "telegram_link_codes", ["user_id"])


def downgrade() -> None:
    op.drop_table("telegram_link_codes")
    with op.batch_alter_table("connector_accounts") as batch:
        batch.drop_column("account_identifier")

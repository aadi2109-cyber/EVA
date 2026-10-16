"""Add connector_accounts.status (replaces the RECONNECT_NEEDED expires_hint prefix).

Revision ID: 002_connector_status
Revises: 001_initial
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "002_connector_status"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("connector_accounts") as batch:
        batch.add_column(sa.Column("status", sa.String(32), nullable=False, server_default="connected"))
    # Carry over rows flagged with the old expires_hint prefix.
    op.execute(
        "UPDATE connector_accounts SET status='reconnect_needed', "
        "expires_hint=TRIM(SUBSTR(expires_hint, LENGTH('RECONNECT_NEEDED')+2)) "
        "WHERE expires_hint LIKE 'RECONNECT_NEEDED%'"
    )


def downgrade() -> None:
    with op.batch_alter_table("connector_accounts") as batch:
        batch.drop_column("status")

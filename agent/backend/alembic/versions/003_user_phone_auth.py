"""Allow phone-only users for MiniMoth OTP authentication.

Revision ID: 003_user_phone_auth
Revises: 002_connector_status
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003_user_phone_auth"
down_revision: Union[str, None] = "002_connector_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.alter_column("email", existing_type=sa.String(255), nullable=True)
        batch.alter_column("hashed_password", existing_type=sa.String(255), nullable=True)
        batch.add_column(sa.Column("phone", sa.String(13), nullable=True))
        batch.create_index("ix_users_phone", ["phone"], unique=True)


def downgrade() -> None:
    # Phone-only users must be removed or linked to email/password accounts before downgrade.
    op.execute("DELETE FROM users WHERE email IS NULL OR hashed_password IS NULL")
    with op.batch_alter_table("users") as batch:
        batch.drop_index("ix_users_phone")
        batch.drop_column("phone")
        batch.alter_column("hashed_password", existing_type=sa.String(255), nullable=False)
        batch.alter_column("email", existing_type=sa.String(255), nullable=False)

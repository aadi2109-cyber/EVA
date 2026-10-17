"""Merge the OTP and Telegram migration branches.

Revision ID: 005_merge_otp_telegram
Revises: 003_telegram_connector, 004_revoked_tokens
"""
from typing import Sequence, Union

revision: str = "005_merge_otp_telegram"
down_revision: Union[str, Sequence[str], None] = ("003_telegram_connector", "004_revoked_tokens")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

"""add direct-cart request fingerprint

Revision ID: 013_direct_product_cart_intent
Revises: 012_customer_onboarding
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "013_direct_product_cart_intent"
down_revision: str | None = "012_customer_onboarding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "runtime_command_receipts",
        sa.Column("request_fingerprint", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("runtime_command_receipts", "request_fingerprint")

"""add monotonic cart versioning

Revision ID: 007_cart_versioning
Revises: 006_order_fulfilment_inventory
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "007_cart_versioning"
down_revision: str | None = "006_order_fulfilment_inventory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "carts",
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("carts", "version")

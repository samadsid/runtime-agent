"""add customer visibility to product categories

Revision ID: 019_category_customer_visibility
Revises: 018_meta_whatsapp_cloud_api
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "019_category_customer_visibility"
down_revision: str | None = "018_meta_whatsapp_cloud_api"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "product_categories",
        sa.Column(
            "customer_visible", sa.Boolean(), server_default=sa.true(), nullable=False
        ),
    )
    op.drop_index("ix_product_categories_browse", table_name="product_categories")
    op.create_index(
        "ix_product_categories_browse",
        "product_categories",
        ["tenant_id", "active", "customer_visible", "display_order", "name", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_product_categories_browse", table_name="product_categories")
    op.create_index(
        "ix_product_categories_browse",
        "product_categories",
        ["tenant_id", "active", "display_order", "name", "id"],
    )
    op.drop_column("product_categories", "customer_visible")

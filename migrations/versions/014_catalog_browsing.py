"""add catalog browsing metadata

Revision ID: 014_catalog_browsing
Revises: 013_direct_product_cart_intent
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "014_catalog_browsing"
down_revision: str | None = "013_direct_product_cart_intent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "id", name="uq_product_categories_tenant_id_id"
        ),
        sa.UniqueConstraint(
            "tenant_id", "name", name="uq_product_categories_tenant_name"
        ),
    )
    op.create_index(
        "ix_product_categories_browse",
        "product_categories",
        ["tenant_id", "active", "display_order", "name", "id"],
    )
    op.add_column(
        "products",
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "products",
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.add_column(
        "products",
        sa.Column(
            "customer_visible", sa.Boolean(), server_default=sa.true(), nullable=False
        ),
    )
    op.add_column(
        "products",
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_unique_constraint(
        "uq_products_tenant_id_id", "products", ["tenant_id", "id"]
    )
    op.create_foreign_key(
        "fk_products_tenant_category",
        "products",
        "product_categories",
        ["tenant_id", "category_id"],
        ["tenant_id", "id"],
    )
    op.create_index(
        "ix_products_catalog_browse",
        "products",
        [
            "tenant_id",
            "category_id",
            "active",
            "customer_visible",
            "display_order",
            "name",
            "id",
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_products_catalog_browse", table_name="products")
    op.drop_constraint("fk_products_tenant_category", "products", type_="foreignkey")
    op.drop_constraint("uq_products_tenant_id_id", "products", type_="unique")
    op.drop_column("products", "display_order")
    op.drop_column("products", "customer_visible")
    op.drop_column("products", "active")
    op.drop_column("products", "category_id")
    op.drop_index("ix_product_categories_browse", table_name="product_categories")
    op.drop_table("product_categories")

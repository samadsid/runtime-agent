"""create durable orders and support completed cart history

Revision ID: 005_create_orders
Revises: 004_create_carts
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005_create_orders"
down_revision: str | None = "004_create_carts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_active_cart_scope", "carts", type_="unique")
    op.create_index(
        "uq_carts_active_scope",
        "carts",
        ["tenant_id", "conversation_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_cart_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("carts.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("payment_method", sa.Text(), nullable=False),
        sa.Column("customer_name", sa.Text(), nullable=False),
        sa.Column("phone_number", sa.Text(), nullable=False),
        sa.Column("delivery_address", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "payment_method = 'CASH_ON_DELIVERY'",
            name="ck_orders_cash_on_delivery",
        ),
    )
    op.create_index(
        "ix_orders_conversation_created_at",
        "orders",
        ["conversation_id", sa.text("created_at DESC")],
    )
    op.create_table(
        "order_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_name", sa.Text(), nullable=False),
        sa.Column("unit", sa.Text(), nullable=False),
        sa.Column("unit_price", sa.Numeric(), nullable=False),
        sa.Column("quantity", sa.Numeric(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_order_items_positive_quantity"),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])


def downgrade() -> None:
    op.drop_index("ix_order_items_order_id", table_name="order_items")
    op.drop_table("order_items")
    op.drop_index("ix_orders_conversation_created_at", table_name="orders")
    op.drop_table("orders")
    op.drop_index("uq_carts_active_scope", table_name="carts")
    op.create_unique_constraint(
        "uq_active_cart_scope",
        "carts",
        ["tenant_id", "conversation_id", "status"],
    )

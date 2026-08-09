"""add order fulfilment inventory and status audit history

Revision ID: 006_order_fulfilment_inventory
Revises: 005_create_orders
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "006_order_fulfilment_inventory"
down_revision: str | None = "005_create_orders"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inventory_balances",
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("products.id"),
            primary_key=True,
        ),
        sa.Column("on_hand_quantity", sa.Numeric(), nullable=False),
        sa.Column(
            "reserved_quantity", sa.Numeric(), nullable=False, server_default="0"
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "on_hand_quantity >= 0", name="ck_inventory_balances_nonnegative_on_hand"
        ),
        sa.CheckConstraint(
            "reserved_quantity >= 0", name="ck_inventory_balances_nonnegative_reserved"
        ),
        sa.CheckConstraint(
            "reserved_quantity <= on_hand_quantity",
            name="ck_inventory_balances_reserved_within_on_hand",
        ),
    )
    op.create_table(
        "inventory_reservations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("products.id"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Numeric(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("quantity > 0", name="ck_inventory_reservations_positive"),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'RELEASED', 'CONSUMED')",
            name="ck_inventory_reservations_status",
        ),
        sa.CheckConstraint(
            "(status = 'ACTIVE' AND released_at IS NULL AND consumed_at IS NULL) OR "
            "(status = 'RELEASED' AND released_at IS NOT NULL AND consumed_at IS NULL) OR "
            "(status = 'CONSUMED' AND consumed_at IS NOT NULL AND released_at IS NULL)",
            name="ck_inventory_reservations_terminal_timestamp",
        ),
        sa.UniqueConstraint(
            "order_id", "product_id", name="uq_reservation_order_product"
        ),
    )
    op.create_index(
        "ix_inventory_reservations_order_id", "inventory_reservations", ["order_id"]
    )
    op.create_index(
        "ix_inventory_reservations_product_status",
        "inventory_reservations",
        ["product_id", "status"],
    )
    op.create_table(
        "order_status_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_status", sa.Text(), nullable=True),
        sa.Column("to_status", sa.Text(), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_type", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "actor_type IN ('CUSTOMER', 'STAFF', 'SYSTEM')",
            name="ck_order_status_history_actor_type",
        ),
    )
    op.create_index(
        "ix_order_status_history_order_id", "order_status_history", ["order_id"]
    )

    # Preserve legacy catalog stock, then account for already-confirmed orders.
    op.execute(
        """
        INSERT INTO inventory_balances (
            product_id, on_hand_quantity, reserved_quantity, updated_at
        )
        SELECT id, stock_quantity, 0, now()
        FROM products
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM inventory_balances AS balance
                JOIN (
                    SELECT item.product_id, SUM(item.quantity) AS quantity
                    FROM order_items AS item
                    JOIN orders AS order_row ON order_row.id = item.order_id
                    WHERE order_row.status = 'CONFIRMED'
                    GROUP BY item.product_id
                ) AS committed ON committed.product_id = balance.product_id
                WHERE committed.quantity > balance.on_hand_quantity
            ) THEN
                RAISE EXCEPTION
                    'Existing confirmed order quantities exceed legacy product stock';
            END IF;
        END $$
        """
    )
    op.execute(
        """
        INSERT INTO inventory_reservations (
            id, order_id, product_id, quantity, status, created_at
        )
        SELECT gen_random_uuid(), item.order_id, item.product_id,
               SUM(item.quantity), 'ACTIVE', order_row.confirmed_at
        FROM order_items AS item
        JOIN orders AS order_row ON order_row.id = item.order_id
        WHERE order_row.status = 'CONFIRMED'
        GROUP BY item.order_id, item.product_id, order_row.confirmed_at
        """
    )
    op.execute(
        """
        UPDATE inventory_balances AS balance
        SET reserved_quantity = committed.quantity, updated_at = now()
        FROM (
            SELECT product_id, SUM(quantity) AS quantity
            FROM inventory_reservations
            WHERE status = 'ACTIVE'
            GROUP BY product_id
        ) AS committed
        WHERE committed.product_id = balance.product_id
        """
    )
    op.execute(
        """
        INSERT INTO order_status_history (
            id, order_id, from_status, to_status, actor_id,
            actor_type, reason, created_at
        )
        SELECT gen_random_uuid(), id, NULL, status, NULL,
               'SYSTEM', 'Backfilled by inventory migration', confirmed_at
        FROM orders
        """
    )


def downgrade() -> None:
    op.drop_index("ix_order_status_history_order_id", table_name="order_status_history")
    op.drop_table("order_status_history")
    op.drop_index(
        "ix_inventory_reservations_product_status",
        table_name="inventory_reservations",
    )
    op.drop_index(
        "ix_inventory_reservations_order_id", table_name="inventory_reservations"
    )
    op.drop_table("inventory_reservations")
    op.drop_table("inventory_balances")

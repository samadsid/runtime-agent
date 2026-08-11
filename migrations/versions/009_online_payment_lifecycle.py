"""add online payment lifecycle

Revision ID: 009_online_payment_lifecycle
Revises: 008_saved_delivery_details
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "009_online_payment_lifecycle"
down_revision: str | None = "008_saved_delivery_details"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_orders_cash_on_delivery", "orders", type_="check")
    op.create_check_constraint(
        "ck_orders_payment_method",
        "orders",
        "payment_method IN ('CASH_ON_DELIVERY', 'ONLINE')",
    )
    op.alter_column(
        "orders",
        "confirmed_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )
    op.add_column("order_items", sa.Column("currency", sa.Text(), nullable=True))
    op.execute(
        """
        UPDATE order_items AS item
        SET currency = product.currency
        FROM products AS product
        WHERE product.id = item.product_id
        """
    )
    op.alter_column("order_items", "currency", existing_type=sa.Text(), nullable=False)

    op.create_table(
        "payment_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("provider_payment_id", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("checkout_url", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("failure_code", sa.Text(), nullable=True),
        sa.Column(
            "reconciliation_attempts", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("reconcile_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_payment_attempts_positive_amount"),
        sa.CheckConstraint(
            "status IN ('CREATING','PENDING','SUCCEEDED','FAILED','EXPIRED','CANCELLED')",
            name="ck_payment_attempts_status",
        ),
        sa.UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_payment_attempt_idempotency"
        ),
        sa.UniqueConstraint(
            "provider",
            "provider_payment_id",
            name="uq_payment_attempt_provider_payment",
        ),
    )
    op.create_index(
        "ix_payment_attempt_order_created",
        "payment_attempts",
        ["tenant_id", "order_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_payment_attempt_status_expiry", "payment_attempts", ["status", "expires_at"]
    )
    op.create_index(
        "uq_payment_attempt_pending_order",
        "payment_attempts",
        ["order_id"],
        unique=True,
        postgresql_where=sa.text("status = 'PENDING'"),
    )

    op.create_table(
        "payment_webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("provider_event_id", sa.Text(), nullable=False),
        sa.Column("provider_payment_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.Column("processing_status", sa.Text(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.UniqueConstraint(
            "provider", "provider_event_id", name="uq_payment_webhook_event"
        ),
    )
    op.create_index(
        "ix_payment_webhook_processing_received",
        "payment_webhook_events",
        ["processing_status", "received_at"],
    )

    op.create_table(
        "fake_provider_payments",
        sa.Column("provider_payment_id", sa.Text(), primary_key=True),
        sa.Column("idempotency_key", sa.Text(), nullable=False, unique=True),
        sa.Column("merchant_reference", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("fake_provider_payments")
    op.drop_index(
        "ix_payment_webhook_processing_received", table_name="payment_webhook_events"
    )
    op.drop_table("payment_webhook_events")
    op.drop_index("uq_payment_attempt_pending_order", table_name="payment_attempts")
    op.drop_index("ix_payment_attempt_status_expiry", table_name="payment_attempts")
    op.drop_index("ix_payment_attempt_order_created", table_name="payment_attempts")
    op.drop_table("payment_attempts")
    op.drop_column("order_items", "currency")
    op.execute(
        """
        UPDATE orders
        SET payment_method = 'CASH_ON_DELIVERY',
            status = CASE
                WHEN status IN ('AWAITING_PAYMENT','PAYMENT_FAILED','PAYMENT_EXPIRED')
                    THEN 'CANCELLED'
                ELSE status
            END,
            confirmed_at = COALESCE(confirmed_at, created_at)
        WHERE payment_method = 'ONLINE' OR confirmed_at IS NULL
        """
    )
    op.alter_column(
        "orders",
        "confirmed_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.drop_constraint("ck_orders_payment_method", "orders", type_="check")
    op.create_check_constraint(
        "ck_orders_cash_on_delivery", "orders", "payment_method = 'CASH_ON_DELIVERY'"
    )

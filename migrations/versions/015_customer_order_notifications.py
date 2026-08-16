"""add transactional customer order notifications

Revision ID: 015_customer_order_notifications
Revises: 014_catalog_browsing
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "015_customer_order_notifications"
down_revision: str | None = "014_catalog_browsing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    timestamp = sa.DateTime(timezone=True)

    op.create_unique_constraint(
        "uq_channel_conversation_tenant_id", "channel_conversations", ["tenant_id", "id"]
    )
    op.create_table(
        "notification_outbox",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("tenant_id", uuid, nullable=False),
        sa.Column("notification_type", sa.Text(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_id", uuid, nullable=False),
        sa.Column("order_id", uuid, sa.ForeignKey("orders.id", ondelete="CASCADE")),
        sa.Column("customer_channel_id", uuid, nullable=True),
        sa.Column("preferred_channel", sa.Text(), nullable=True),
        sa.Column("locale", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("payload_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", timestamp, nullable=False),
        sa.Column("lease_expires_at", timestamp, nullable=True),
        sa.Column("last_error_code", sa.Text(), nullable=True),
        sa.Column("created_at", timestamp, nullable=False),
        sa.Column("processed_at", timestamp, nullable=True),
        sa.CheckConstraint("attempt_count >= 0", name="ck_notification_attempt_count"),
        sa.CheckConstraint(
            "status IN ('PENDING','PROCESSING','RETRYABLE','DISPATCHED','DEAD_LETTER','SUPPRESSED')",
            name="ck_notification_status",
        ),
        sa.CheckConstraint(
            "source_type IN ('ORDER_STATUS_HISTORY','PAYMENT_EVENT')",
            name="ck_notification_source_type",
        ),
        sa.UniqueConstraint(
            "tenant_id", "source_type", "source_id", "notification_type",
            name="uq_notification_logical_event",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "customer_channel_id"],
            ["channel_conversations.tenant_id", "channel_conversations.id"],
            name="fk_notification_tenant_channel",
        ),
    )
    op.create_index(
        "ix_notification_claim", "notification_outbox",
        ["status", "available_at", "created_at"],
    )
    op.create_index(
        "ix_notification_order", "notification_outbox",
        ["tenant_id", "order_id", "created_at"],
    )

    op.alter_column(
        "channel_outbound_messages", "source_inbound_id",
        existing_type=uuid, nullable=True,
    )
    op.alter_column(
        "channel_outbound_messages", "body",
        existing_type=sa.Text(), nullable=True,
    )
    op.add_column(
        "channel_outbound_messages",
        sa.Column("content_mode", sa.Text(), nullable=False, server_default="TEXT"),
    )
    op.add_column(
        "channel_outbound_messages", sa.Column("content_sid", sa.Text(), nullable=True)
    )
    op.add_column(
        "channel_outbound_messages",
        sa.Column("content_variables", postgresql.JSONB(), nullable=True),
    )
    op.create_check_constraint(
        "ck_channel_outbound_content",
        "channel_outbound_messages",
        "(content_mode='TEXT' AND body IS NOT NULL AND content_sid IS NULL AND content_variables IS NULL) OR "
        "(content_mode='TEMPLATE' AND content_sid IS NOT NULL AND content_variables IS NOT NULL)",
    )

    op.create_table(
        "notification_deliveries",
        sa.Column("id", uuid, primary_key=True),
        sa.Column(
            "notification_id", uuid,
            sa.ForeignKey("notification_outbox.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column(
            "channel_outbound_message_id", uuid,
            sa.ForeignKey("channel_outbound_messages.id", ondelete="CASCADE"),
            nullable=False, unique=True,
        ),
        sa.Column("template_key", sa.Text(), nullable=False),
        sa.Column("template_version", sa.Integer(), nullable=False),
        sa.Column("created_at", timestamp, nullable=False),
        sa.UniqueConstraint("notification_id", "channel", name="uq_notification_delivery_channel"),
    )

    # Establish a safe rollout baseline without sending historical status changes.
    op.execute(
        """
        INSERT INTO notification_outbox (
            id, tenant_id, notification_type, source_type, source_id, order_id,
            customer_channel_id, preferred_channel, locale, payload, payload_version,
            status, attempt_count, available_at, last_error_code, created_at, processed_at
        )
        SELECT gen_random_uuid(), cart.tenant_id,
               CASE history.to_status
                   WHEN 'CONFIRMED' THEN 'ORDER_CONFIRMED'
                   WHEN 'PREPARING' THEN 'ORDER_PREPARING'
                   WHEN 'OUT_FOR_DELIVERY' THEN 'ORDER_OUT_FOR_DELIVERY'
                   WHEN 'DELIVERED' THEN 'ORDER_DELIVERED'
                   WHEN 'CANCELLED' THEN 'ORDER_CANCELLED'
               END,
               'ORDER_STATUS_HISTORY', history.id, order_row.id,
               channel.id, COALESCE(channel.channel, 'development_http'), NULL,
               jsonb_build_object(
                   'version', 1,
                   'order_reference', order_row.id::text,
                   'order_status', history.to_status,
                   'payment_method', order_row.payment_method,
                   'currency', totals.currency,
                   'total_amount', totals.total_amount::text,
                   'occurred_at', to_jsonb(history.created_at)
               ),
               1, 'SUPPRESSED', 0, history.created_at, 'pre_feature_history',
               history.created_at, now()
        FROM order_status_history history
        JOIN orders order_row ON order_row.id=history.order_id
        JOIN carts cart ON cart.id=order_row.source_cart_id
        JOIN LATERAL (
            SELECT MIN(currency) AS currency,
                   SUM(unit_price * quantity) AS total_amount
            FROM order_items WHERE order_id=order_row.id
        ) totals ON TRUE
        LEFT JOIN channel_conversations channel
          ON channel.tenant_id=cart.tenant_id
         AND channel.conversation_id=order_row.conversation_id
        WHERE history.to_status IN (
            'CONFIRMED','PREPARING','OUT_FOR_DELIVERY','DELIVERED','CANCELLED'
        )
        """
    )


def downgrade() -> None:
    op.drop_table("notification_deliveries")
    op.execute("DELETE FROM channel_outbound_messages WHERE source_inbound_id IS NULL")
    op.drop_constraint(
        "ck_channel_outbound_content", "channel_outbound_messages", type_="check"
    )
    op.drop_column("channel_outbound_messages", "content_variables")
    op.drop_column("channel_outbound_messages", "content_sid")
    op.drop_column("channel_outbound_messages", "content_mode")
    op.alter_column(
        "channel_outbound_messages", "body", existing_type=sa.Text(), nullable=False
    )
    op.alter_column(
        "channel_outbound_messages",
        "source_inbound_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.drop_index("ix_notification_order", table_name="notification_outbox")
    op.drop_index("ix_notification_claim", table_name="notification_outbox")
    op.drop_table("notification_outbox")
    op.drop_constraint(
        "uq_channel_conversation_tenant_id", "channel_conversations", type_="unique"
    )

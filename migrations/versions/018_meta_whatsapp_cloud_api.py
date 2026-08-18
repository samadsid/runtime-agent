"""add provider-neutral WhatsApp transport and Meta Cloud API persistence

Revision ID: 018_meta_whatsapp_cloud_api
Revises: 017_catalog_inventory_admin
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "018_meta_whatsapp_cloud_api"
down_revision: str | None = "017_catalog_inventory_admin"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM channel_conversations old
            JOIN channel_conversations current
              ON current.tenant_id=old.tenant_id
             AND current.channel_customer_id=old.channel_customer_id
             AND current.channel='whatsapp'
            WHERE old.channel='twilio_whatsapp'
          ) OR EXISTS (
            SELECT 1 FROM saved_delivery_profiles old
            JOIN saved_delivery_profiles current
              ON current.tenant_id=old.tenant_id
             AND current.channel_customer_id=old.channel_customer_id
             AND current.channel='whatsapp'
            WHERE old.channel='twilio_whatsapp'
          ) THEN
            RAISE EXCEPTION 'WhatsApp identity collision requires explicit disposition';
          END IF;
        END $$;
        """
    )
    for table in (
        "channel_inbound_messages",
        "channel_outbound_messages",
        "channel_delivery_events",
    ):
        op.add_column(
            table,
            sa.Column("provider", sa.Text(), nullable=False, server_default="twilio"),
        )
        op.create_check_constraint(
            f"ck_{table}_provider",
            table,
            "provider IN ('twilio','meta_cloud')",
        )
        op.alter_column(table, "provider", server_default=None)

    op.drop_constraint(
        "uq_channel_inbound_provider_message",
        "channel_inbound_messages",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_channel_inbound_provider_message",
        "channel_inbound_messages",
        ["provider", "provider_message_id"],
    )
    op.drop_constraint(
        "uq_channel_outbound_provider_message",
        "channel_outbound_messages",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_channel_outbound_provider_message",
        "channel_outbound_messages",
        ["provider", "provider_message_id"],
    )
    op.drop_constraint(
        "uq_channel_delivery_event", "channel_delivery_events", type_="unique"
    )
    op.add_column(
        "channel_delivery_events",
        sa.Column("provider_event_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        """CREATE UNIQUE INDEX uq_channel_delivery_event
           ON channel_delivery_events (
             provider,provider_message_id,status,
             COALESCE(provider_event_at,'-infinity'::timestamptz),
             left(COALESCE(error_code,''),64)
           )"""
    )
    op.add_column(
        "channel_outbound_messages", sa.Column("template_key", sa.Text(), nullable=True)
    )
    op.add_column(
        "channel_outbound_messages",
        sa.Column("send_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "channel_outbound_messages",
        sa.Column("template_name", sa.Text(), nullable=True),
    )
    op.add_column(
        "channel_outbound_messages",
        sa.Column("template_language", sa.Text(), nullable=True),
    )
    op.execute(
        "UPDATE channel_outbound_messages SET template_name=content_sid WHERE content_mode='TEMPLATE'"
    )
    op.execute(
        "UPDATE channel_conversations SET channel='whatsapp' WHERE channel='twilio_whatsapp'"
    )
    op.execute(
        "UPDATE channel_inbound_messages SET channel='whatsapp' WHERE channel='twilio_whatsapp'"
    )
    op.execute(
        "UPDATE channel_outbound_messages SET channel='whatsapp' WHERE channel='twilio_whatsapp'"
    )
    op.execute(
        "UPDATE channel_delivery_events SET channel='whatsapp' WHERE channel='twilio_whatsapp'"
    )
    op.execute(
        "UPDATE saved_delivery_profiles SET channel='whatsapp' WHERE channel='twilio_whatsapp'"
    )
    op.execute(
        "UPDATE notification_outbox SET preferred_channel='whatsapp' WHERE preferred_channel='twilio_whatsapp'"
    )
    op.execute(
        "UPDATE notification_deliveries SET channel='whatsapp' WHERE channel='twilio_whatsapp'"
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM channel_inbound_messages WHERE provider='meta_cloud')
             OR EXISTS (SELECT 1 FROM channel_outbound_messages WHERE provider='meta_cloud')
             OR EXISTS (SELECT 1 FROM channel_delivery_events WHERE provider='meta_cloud') THEN
            RAISE EXCEPTION 'Refusing downgrade while Meta WhatsApp rows exist';
          END IF;
        END $$;
        """
    )
    op.execute(
        "UPDATE channel_conversations SET channel='twilio_whatsapp' WHERE channel='whatsapp'"
    )
    op.execute(
        "UPDATE channel_inbound_messages SET channel='twilio_whatsapp' WHERE channel='whatsapp'"
    )
    op.execute(
        "UPDATE channel_outbound_messages SET channel='twilio_whatsapp' WHERE channel='whatsapp'"
    )
    op.execute(
        "UPDATE channel_delivery_events SET channel='twilio_whatsapp' WHERE channel='whatsapp'"
    )
    op.execute(
        "UPDATE saved_delivery_profiles SET channel='twilio_whatsapp' WHERE channel='whatsapp'"
    )
    op.execute(
        "UPDATE notification_outbox SET preferred_channel='twilio_whatsapp' WHERE preferred_channel='whatsapp'"
    )
    op.execute(
        "UPDATE notification_deliveries SET channel='twilio_whatsapp' WHERE channel='whatsapp'"
    )
    op.drop_column("channel_outbound_messages", "template_language")
    op.drop_column("channel_outbound_messages", "template_name")
    op.drop_column("channel_outbound_messages", "send_started_at")
    op.drop_column("channel_outbound_messages", "template_key")
    op.drop_index("uq_channel_delivery_event", table_name="channel_delivery_events")
    op.drop_column("channel_delivery_events", "provider_event_at")
    op.create_unique_constraint(
        "uq_channel_delivery_event",
        "channel_delivery_events",
        ["channel", "provider_message_id", "status"],
    )
    op.drop_constraint(
        "uq_channel_outbound_provider_message",
        "channel_outbound_messages",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_channel_outbound_provider_message",
        "channel_outbound_messages",
        ["channel", "provider_message_id"],
    )
    op.drop_constraint(
        "uq_channel_inbound_provider_message",
        "channel_inbound_messages",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_channel_inbound_provider_message",
        "channel_inbound_messages",
        ["channel", "provider_message_id"],
    )
    for table in (
        "channel_delivery_events",
        "channel_outbound_messages",
        "channel_inbound_messages",
    ):
        op.drop_constraint(f"ck_{table}_provider", table, type_="check")
        op.drop_column(table, "provider")

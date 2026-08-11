"""add durable conversational channel inbox and outbox

Revision ID: 010_twilio_whatsapp_channel
Revises: 009_online_payment_lifecycle
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "010_twilio_whatsapp_channel"
down_revision: str | None = "009_online_payment_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    timestamp = sa.DateTime(timezone=True)
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "channel_conversations",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("tenant_id", uuid, nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("channel_customer_id", sa.Text(), nullable=False),
        sa.Column("conversation_id", uuid, nullable=False),
        sa.Column("last_inbound_at", timestamp, nullable=False),
        sa.Column("created_at", timestamp, nullable=False),
        sa.Column("updated_at", timestamp, nullable=False),
        sa.UniqueConstraint(
            "tenant_id",
            "channel",
            "channel_customer_id",
            name="uq_channel_conversation_identity",
        ),
        sa.UniqueConstraint(
            "tenant_id", "conversation_id", name="uq_channel_conversation_thread"
        ),
    )
    op.create_table(
        "channel_inbound_messages",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("tenant_id", uuid, nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("provider_message_id", sa.Text(), nullable=False),
        sa.Column("conversation_id", uuid, nullable=False),
        sa.Column("sender_id", sa.Text(), nullable=False),
        sa.Column("recipient_id", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("message_kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", timestamp, nullable=False),
        sa.Column("lease_expires_at", timestamp, nullable=True),
        sa.Column("last_error_code", sa.Text(), nullable=True),
        sa.Column("received_at", timestamp, nullable=False),
        sa.Column("processed_at", timestamp, nullable=True),
        sa.CheckConstraint(
            "message_kind IN ('TEXT','UNSUPPORTED')", name="ck_channel_inbound_kind"
        ),
        sa.CheckConstraint(
            "status IN ('RECEIVED','PROCESSING','RETRYABLE','PROCESSED','DEAD_LETTER')",
            name="ck_channel_inbound_status",
        ),
        sa.UniqueConstraint(
            "channel", "provider_message_id", name="uq_channel_inbound_provider_message"
        ),
    )
    op.create_index(
        "ix_channel_inbound_claim",
        "channel_inbound_messages",
        ["status", "next_attempt_at", "received_at"],
    )
    op.create_index(
        "ix_channel_inbound_conversation",
        "channel_inbound_messages",
        ["tenant_id", "conversation_id", "received_at"],
    )
    op.create_table(
        "channel_outbound_messages",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("tenant_id", uuid, nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("conversation_id", uuid, nullable=False),
        sa.Column(
            "source_inbound_id",
            uuid,
            sa.ForeignKey("channel_inbound_messages.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("recipient_id", sa.Text(), nullable=False),
        sa.Column("sender_id", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("provider_message_id", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", timestamp, nullable=False),
        sa.Column("lease_expires_at", timestamp, nullable=True),
        sa.Column("last_error_code", sa.Text(), nullable=True),
        sa.Column("created_at", timestamp, nullable=False),
        sa.Column("sent_at", timestamp, nullable=True),
        sa.Column("updated_at", timestamp, nullable=False),
        sa.CheckConstraint(
            "status IN ('PENDING','SENDING','RETRYABLE','ACCEPTED','SENT','DELIVERED','READ','FAILED','DEAD_LETTER','TEMPLATE_REQUIRED','AMBIGUOUS')",
            name="ck_channel_outbound_status",
        ),
        sa.UniqueConstraint(
            "channel",
            "provider_message_id",
            name="uq_channel_outbound_provider_message",
        ),
    )
    op.create_index(
        "ix_channel_outbound_claim",
        "channel_outbound_messages",
        ["status", "next_attempt_at", "created_at"],
    )
    op.create_table(
        "channel_delivery_events",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("provider_message_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("received_at", timestamp, nullable=False),
        sa.UniqueConstraint(
            "channel", "provider_message_id", "status", name="uq_channel_delivery_event"
        ),
    )
    op.create_table(
        "runtime_command_receipts",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("tenant_id", uuid, nullable=False),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("operation", sa.Text(), nullable=False),
        sa.Column("result_payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", timestamp, nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "request_id", "operation", name="uq_runtime_command_receipt"
        ),
    )


def downgrade() -> None:
    op.drop_table("runtime_command_receipts")
    op.drop_table("channel_delivery_events")
    op.drop_index("ix_channel_outbound_claim", table_name="channel_outbound_messages")
    op.drop_table("channel_outbound_messages")
    op.drop_index(
        "ix_channel_inbound_conversation", table_name="channel_inbound_messages"
    )
    op.drop_index("ix_channel_inbound_claim", table_name="channel_inbound_messages")
    op.drop_table("channel_inbound_messages")
    op.drop_table("channel_conversations")

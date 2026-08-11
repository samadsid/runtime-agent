"""add REST chat request idempotency

Revision ID: 011_customer_web_chat
Revises: 010_twilio_whatsapp_channel
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "011_customer_web_chat"
down_revision: str | None = "010_twilio_whatsapp_channel"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    timestamp = sa.DateTime(timezone=True)
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "rest_chat_requests",
        sa.Column("tenant_id", uuid, nullable=False),
        sa.Column("request_id", uuid, nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("conversation_id", uuid, nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("reply", sa.Text(), nullable=True),
        sa.Column("created_at", timestamp, nullable=False),
        sa.Column("updated_at", timestamp, nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "request_id"),
        sa.CheckConstraint(
            "status IN ('PENDING','EXECUTING','COMPLETED','AMBIGUOUS')",
            name="ck_rest_chat_request_status",
        ),
    )
    op.create_index(
        "ix_rest_chat_request_retention", "rest_chat_requests", ["updated_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_rest_chat_request_retention", table_name="rest_chat_requests")
    op.drop_table("rest_chat_requests")

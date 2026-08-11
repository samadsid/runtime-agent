"""add saved delivery profiles and addresses

Revision ID: 008_saved_delivery_details
Revises: 007_cart_versioning
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "008_saved_delivery_details"
down_revision: str | None = "007_cart_versioning"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "saved_delivery_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("channel_customer_id", sa.Text(), nullable=False),
        sa.Column("customer_name", sa.Text(), nullable=True),
        sa.Column("phone_number", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id",
            "channel",
            "channel_customer_id",
            name="uq_saved_delivery_profile_identity",
        ),
    )
    op.create_table(
        "saved_delivery_addresses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("saved_delivery_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("delivery_address", sa.Text(), nullable=False),
        sa.Column(
            "is_default", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "btrim(label) <> ''", name="ck_saved_address_label_nonempty"
        ),
        sa.CheckConstraint(
            "btrim(delivery_address) <> ''", name="ck_saved_address_text_nonempty"
        ),
        sa.CheckConstraint("version >= 1", name="ck_saved_address_version_positive"),
    )
    op.create_index(
        "ix_saved_addresses_profile_created",
        "saved_delivery_addresses",
        ["profile_id", "created_at", "id"],
    )
    op.create_index(
        "uq_saved_addresses_one_default",
        "saved_delivery_addresses",
        ["profile_id"],
        unique=True,
        postgresql_where=sa.text("is_default = TRUE"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_saved_addresses_one_default", table_name="saved_delivery_addresses"
    )
    op.drop_index(
        "ix_saved_addresses_profile_created", table_name="saved_delivery_addresses"
    )
    op.drop_table("saved_delivery_addresses")
    op.drop_table("saved_delivery_profiles")

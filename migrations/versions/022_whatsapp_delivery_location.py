"""add WhatsApp delivery locations and tenant delivery zones

Revision ID: 022_delivery_location
Revises: 021_checkout_public_orders
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "022_delivery_location"
down_revision: str | None = "021_checkout_public_orders"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.drop_constraint(
        "ck_channel_inbound_kind", "channel_inbound_messages", type_="check"
    )
    op.add_column(
        "channel_inbound_messages",
        sa.Column("location_latitude", sa.Numeric(9, 6), nullable=True),
    )
    op.add_column(
        "channel_inbound_messages",
        sa.Column("location_longitude", sa.Numeric(9, 6), nullable=True),
    )
    op.add_column(
        "channel_inbound_messages",
        sa.Column("location_name", sa.String(200), nullable=True),
    )
    op.add_column(
        "channel_inbound_messages",
        sa.Column("location_provider_address", sa.String(500), nullable=True),
    )
    op.create_check_constraint(
        "ck_channel_inbound_kind",
        "channel_inbound_messages",
        "message_kind IN ('TEXT','LOCATION','UNSUPPORTED')",
    )
    op.create_check_constraint(
        "ck_channel_inbound_location_contract",
        "channel_inbound_messages",
        """(message_kind = 'LOCATION'
              AND location_latitude BETWEEN -90 AND 90
              AND location_longitude BETWEEN -180 AND 180)
           OR (message_kind <> 'LOCATION'
              AND location_latitude IS NULL AND location_longitude IS NULL
              AND location_name IS NULL AND location_provider_address IS NULL)""",
    )

    op.execute(
        """
        CREATE TABLE delivery_zones (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL,
            name varchar(120) NOT NULL,
            name_normalized varchar(120) NOT NULL,
            status varchar(16) NOT NULL,
            priority integer NOT NULL DEFAULT 100,
            boundary geometry(MultiPolygon,4326) NOT NULL,
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL,
            CONSTRAINT ck_delivery_zone_status
                CHECK (status IN ('DRAFT','ACTIVE','INACTIVE')),
            CONSTRAINT ck_delivery_zone_priority CHECK (priority >= 0),
            CONSTRAINT ck_delivery_zone_version CHECK (version >= 1),
            CONSTRAINT ck_delivery_zone_not_empty CHECK (NOT ST_IsEmpty(boundary)),
            CONSTRAINT ck_delivery_zone_valid CHECK (ST_IsValid(boundary)),
            CONSTRAINT uq_delivery_zone_tenant_name
                UNIQUE (tenant_id,name_normalized)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_delivery_zones_boundary ON delivery_zones USING gist(boundary)"
    )
    op.create_index(
        "ix_delivery_zones_tenant_status_priority",
        "delivery_zones",
        ["tenant_id", "status", "priority", "id"],
    )
    op.create_table(
        "delivery_zone_audit",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("zone_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.String(16), nullable=False),
        sa.Column("from_version", sa.Integer(), nullable=True),
        sa.Column("to_version", sa.Integer(), nullable=False),
        sa.Column("geometry_hash", sa.String(64), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["zone_id"], ["delivery_zones.id"]),
        sa.CheckConstraint(
            "operation IN ('CREATED','UPDATED','ACTIVATED','DEACTIVATED')",
            name="ck_delivery_zone_audit_operation",
        ),
    )
    op.create_index(
        "ix_delivery_zone_audit_zone",
        "delivery_zone_audit",
        ["tenant_id", "zone_id", sa.text("created_at DESC")],
    )

    for table in ("saved_delivery_addresses", "orders"):
        op.add_column(table, sa.Column("location_latitude", sa.Numeric(9, 6)))
        op.add_column(table, sa.Column("location_longitude", sa.Numeric(9, 6)))
        op.add_column(table, sa.Column("location_formatted_area", sa.String(500)))
        op.add_column(table, sa.Column("location_address_details", sa.String(500)))
        op.add_column(
            table, sa.Column("location_zone_id", postgresql.UUID(as_uuid=True))
        )
        op.add_column(table, sa.Column("location_zone_name", sa.String(120)))
        op.add_column(table, sa.Column("location_zone_version", sa.Integer()))
        op.add_column(
            table, sa.Column("location_checked_at", sa.DateTime(timezone=True))
        )
        op.create_check_constraint(
            f"ck_{table}_location_complete",
            table,
            """(location_latitude IS NULL AND location_longitude IS NULL
                 AND location_zone_id IS NULL AND location_zone_name IS NULL
                 AND location_zone_version IS NULL AND location_checked_at IS NULL)
                OR (location_latitude BETWEEN -90 AND 90
                 AND location_longitude BETWEEN -180 AND 180
                 AND location_zone_id IS NOT NULL AND location_zone_name IS NOT NULL
                 AND location_zone_version >= 1 AND location_checked_at IS NOT NULL)""",
        )
    op.add_column(
        "saved_delivery_addresses",
        sa.Column(
            "serviceability_status",
            sa.String(32),
            nullable=False,
            server_default="LEGACY_UNVALIDATED",
        ),
    )
    op.create_check_constraint(
        "ck_saved_address_serviceability_status",
        "saved_delivery_addresses",
        "serviceability_status IN ('SERVICEABLE','REVALIDATION_REQUIRED','LEGACY_UNVALIDATED')",
    )


def downgrade() -> None:
    connection = op.get_bind()
    has_data = connection.execute(
        sa.text(
            """SELECT EXISTS(SELECT 1 FROM delivery_zones)
                OR EXISTS(SELECT 1 FROM saved_delivery_addresses
                          WHERE location_latitude IS NOT NULL)
                OR EXISTS(SELECT 1 FROM orders WHERE location_latitude IS NOT NULL)"""
        )
    ).scalar()
    if has_data:
        raise RuntimeError(
            "Refusing to discard delivery-zone or precise-location data during downgrade."
        )
    op.drop_constraint(
        "ck_saved_address_serviceability_status",
        "saved_delivery_addresses",
        type_="check",
    )
    op.drop_column("saved_delivery_addresses", "serviceability_status")
    for table in ("orders", "saved_delivery_addresses"):
        op.drop_constraint(f"ck_{table}_location_complete", table, type_="check")
        for column in (
            "location_checked_at",
            "location_zone_version",
            "location_zone_name",
            "location_zone_id",
            "location_formatted_area",
            "location_address_details",
            "location_longitude",
            "location_latitude",
        ):
            op.drop_column(table, column)
    op.drop_index("ix_delivery_zone_audit_zone", table_name="delivery_zone_audit")
    op.drop_table("delivery_zone_audit")
    op.drop_index(
        "ix_delivery_zones_tenant_status_priority", table_name="delivery_zones"
    )
    op.execute("DROP INDEX ix_delivery_zones_boundary")
    op.drop_table("delivery_zones")
    op.drop_constraint(
        "ck_channel_inbound_location_contract",
        "channel_inbound_messages",
        type_="check",
    )
    for column in (
        "location_provider_address",
        "location_name",
        "location_longitude",
        "location_latitude",
    ):
        op.drop_column("channel_inbound_messages", column)
    op.drop_constraint(
        "ck_channel_inbound_kind", "channel_inbound_messages", type_="check"
    )
    op.create_check_constraint(
        "ck_channel_inbound_kind",
        "channel_inbound_messages",
        "message_kind IN ('TEXT','UNSUPPORTED')",
    )

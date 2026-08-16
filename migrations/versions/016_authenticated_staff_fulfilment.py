"""add authenticated staff fulfilment API persistence

Revision ID: 016_authenticated_staff_fulfilment
Revises: 015_customer_order_notifications
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "016_authenticated_staff_fulfilment"
down_revision: str | None = "015_customer_order_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    timestamp = sa.DateTime(timezone=True)

    op.create_table(
        "staff_accounts",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("email_normalized", sa.Text(), nullable=False, unique=True),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", timestamp, nullable=False),
        sa.Column("updated_at", timestamp, nullable=False),
        sa.CheckConstraint(
            "status IN ('ACTIVE','DISABLED')", name="ck_staff_accounts_status"
        ),
    )
    op.create_table(
        "staff_tenant_memberships",
        sa.Column(
            "staff_id", uuid, sa.ForeignKey("staff_accounts.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("tenant_id", uuid, primary_key=True),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", timestamp, nullable=False),
        sa.Column("updated_at", timestamp, nullable=False),
        sa.CheckConstraint(
            "role IN ('ADMIN','FULFILMENT_STAFF')",
            name="ck_staff_tenant_memberships_role",
        ),
    )
    op.create_index(
        "ix_staff_memberships_tenant_active_role",
        "staff_tenant_memberships",
        ["tenant_id", "active", "role"],
    )
    op.add_column(
        "orders", sa.Column("version", sa.Integer(), nullable=False, server_default="1")
    )
    op.add_column(
        "orders",
        sa.Column("updated_at", timestamp, nullable=True, server_default=sa.func.now()),
    )
    op.execute(
        """
        UPDATE orders AS order_row
        SET updated_at = COALESCE(
            (SELECT MAX(history.created_at) FROM order_status_history AS history
             WHERE history.order_id = order_row.id),
            order_row.created_at
        )
        """
    )
    op.alter_column("orders", "updated_at", existing_type=timestamp, nullable=False)
    op.create_check_constraint("ck_orders_version_positive", "orders", "version >= 1")
    op.create_index(
        "ix_orders_staff_cursor", "orders", [sa.text("created_at DESC"), sa.text("id DESC")]
    )
    op.create_table(
        "staff_api_idempotency",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("tenant_id", uuid, nullable=False),
        sa.Column(
            "staff_id", uuid, sa.ForeignKey("staff_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("operation", sa.Text(), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("resource_id", uuid, nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", timestamp, nullable=False),
        sa.Column("expires_at", timestamp, nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "staff_id", "idempotency_key",
            name="uq_staff_api_idempotency_key",
        ),
    )
    op.create_index(
        "ix_staff_api_idempotency_expires", "staff_api_idempotency", ["expires_at"]
    )
    op.create_table(
        "staff_rate_limit_buckets",
        sa.Column("bucket_key", sa.String(length=64), primary_key=True),
        sa.Column("window_started_at", timestamp, nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("expires_at", timestamp, nullable=False),
        sa.CheckConstraint("request_count >= 1", name="ck_staff_rate_limit_count"),
    )
    op.create_index(
        "ix_staff_rate_limit_expires", "staff_rate_limit_buckets", ["expires_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_staff_rate_limit_expires", table_name="staff_rate_limit_buckets")
    op.drop_table("staff_rate_limit_buckets")
    op.drop_index("ix_staff_api_idempotency_expires", table_name="staff_api_idempotency")
    op.drop_table("staff_api_idempotency")
    op.drop_index("ix_orders_staff_cursor", table_name="orders")
    op.drop_constraint("ck_orders_version_positive", "orders", type_="check")
    op.drop_column("orders", "updated_at")
    op.drop_column("orders", "version")
    op.drop_index(
        "ix_staff_memberships_tenant_active_role", table_name="staff_tenant_memberships"
    )
    op.drop_table("staff_tenant_memberships")
    op.drop_table("staff_accounts")

"""add tenant-scoped public order numbers

Revision ID: 021_checkout_public_orders
Revises: 020_seed_default_meat_category
"""

import os
import re
from collections.abc import Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from alembic import context, op

revision: str = "021_checkout_public_orders"
down_revision: str | None = "020_seed_default_meat_category"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _configuration() -> tuple[str, str]:
    arguments = context.get_x_argument(as_dictionary=True)
    prefix = arguments.get(
        "public_order_prefix", os.getenv("PUBLIC_ORDER_NUMBER_PREFIX", "MU")
    )
    timezone = arguments.get(
        "business_timezone", os.getenv("BUSINESS_TIMEZONE", "Asia/Kolkata")
    )
    if re.fullmatch(r"[A-Z0-9]{1,8}", prefix) is None:
        raise ValueError("Invalid public order prefix.")
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as error:
        raise ValueError("Invalid business timezone.") from error
    return prefix, timezone


def upgrade() -> None:
    prefix, timezone = _configuration()
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS tenant_id uuid")
    op.execute(
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS public_order_number varchar(32)"
    )
    op.execute(
        """
        UPDATE orders AS order_row
        SET tenant_id = cart.tenant_id
        FROM carts AS cart
        WHERE cart.id = order_row.source_cart_id
          AND order_row.tenant_id IS NULL
        """
    )
    op.execute(
        "CREATE SEQUENCE IF NOT EXISTS public_order_number_seq AS bigint START WITH 1"
    )
    escaped_timezone = timezone.replace("'", "''")
    escaped_prefix = prefix.replace("'", "''")
    op.execute(
        f"""
        DO $$
        DECLARE order_record record;
        DECLARE allocated bigint;
        BEGIN
          FOR order_record IN
            SELECT id, created_at FROM orders
            WHERE public_order_number IS NULL
            ORDER BY created_at, id
          LOOP
            allocated := nextval('public_order_number_seq');
            UPDATE orders
            SET public_order_number = '{escaped_prefix}-' ||
                to_char(order_record.created_at AT TIME ZONE '{escaped_timezone}', 'YYMMDD') ||
                '-' || lpad(allocated::text, 4, '0')
            WHERE id = order_record.id;
          END LOOP;
        END $$
        """
    )
    op.alter_column("orders", "tenant_id", nullable=False)
    op.alter_column("orders", "public_order_number", nullable=False)
    op.create_check_constraint(
        "ck_orders_public_order_number_format",
        "orders",
        "public_order_number ~ '^[A-Z0-9]{1,8}-[0-9]{6}-[0-9]{4,}$'",
    )
    op.create_unique_constraint(
        "uq_orders_tenant_public_order_number",
        "orders",
        ["tenant_id", "public_order_number"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_orders_tenant_public_order_number", "orders", type_="unique"
    )
    op.drop_constraint(
        "ck_orders_public_order_number_format", "orders", type_="check"
    )
    op.alter_column("orders", "public_order_number", nullable=True)
    op.alter_column("orders", "tenant_id", nullable=True)
    # Columns and sequence deliberately remain so downgrade/re-upgrade neither
    # destroys nor reallocates already-published customer identities.

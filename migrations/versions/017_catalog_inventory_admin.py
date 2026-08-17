"""add catalog and inventory administration

Revision ID: 017_catalog_inventory_admin
Revises: 016_staff_fulfilment_auth
"""

import unicodedata
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "017_catalog_inventory_admin"
down_revision: str | None = "016_staff_fulfilment_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    timestamp = sa.DateTime(timezone=True)

    # Abort before DDL if legacy data cannot be migrated without changing identity/stock.
    connection = op.get_bind()
    normalized_skus: dict[object, str] = {}
    seen: set[tuple[object, str]] = set()
    for row in connection.execute(sa.text("SELECT id,tenant_id,sku FROM products")).mappings():
        normalized = " ".join(unicodedata.normalize("NFKC", row["sku"]).strip().split()).casefold()
        identity = (row["tenant_id"], normalized)
        if not normalized or identity in seen:
            raise RuntimeError("duplicate or empty normalized tenant SKU")
        seen.add(identity)
        normalized_skus[row["id"]] = normalized
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (
            SELECT 1 FROM inventory_balances
            WHERE on_hand_quantity < 0 OR reserved_quantity < 0
               OR reserved_quantity > on_hand_quantity
          ) THEN RAISE EXCEPTION 'invalid legacy inventory balance'; END IF;
        END $$
    """)

    op.add_column("products", sa.Column("status", sa.Text(), nullable=True))
    op.add_column("products", sa.Column("sku_normalized", sa.Text(), nullable=True))
    op.add_column("products", sa.Column("low_stock_threshold", sa.Numeric(), nullable=True))
    op.add_column("products", sa.Column("version", sa.Integer(), server_default="1", nullable=False))
    op.execute("UPDATE products SET status = CASE WHEN available THEN 'ACTIVE' ELSE 'INACTIVE' END")
    for product_id, normalized in normalized_skus.items():
        connection.execute(
            sa.text("UPDATE products SET sku_normalized=:normalized WHERE id=:product_id"),
            {"normalized": normalized, "product_id": product_id},
        )
    op.alter_column("products", "status", nullable=False)
    op.alter_column("products", "sku_normalized", nullable=False)
    op.create_check_constraint("ck_products_status", "products", "status IN ('ACTIVE','INACTIVE')")
    op.create_check_constraint("ck_products_price_nonnegative", "products", "price >= 0")
    op.create_check_constraint("ck_products_threshold_nonnegative", "products", "low_stock_threshold IS NULL OR low_stock_threshold >= 0")
    op.create_check_constraint("ck_products_display_order_nonnegative", "products", "display_order >= 0")
    op.create_check_constraint("ck_products_version_positive", "products", "version >= 1")
    op.create_unique_constraint("uq_products_tenant_sku_normalized", "products", ["tenant_id", "sku_normalized"])
    op.create_index("ix_products_admin_list", "products", ["tenant_id", "status", "category_id", "display_order", "name", "id"])
    op.drop_column("products", "available")

    op.add_column("inventory_balances", sa.Column("tenant_id", uuid, nullable=True))
    op.add_column("inventory_balances", sa.Column("version", sa.Integer(), server_default="1", nullable=False))
    op.execute("""UPDATE inventory_balances b SET tenant_id=p.tenant_id FROM products p WHERE p.id=b.product_id""")
    op.alter_column("inventory_balances", "tenant_id", nullable=False)
    op.create_unique_constraint("uq_inventory_balance_tenant_product", "inventory_balances", ["tenant_id", "product_id"])
    op.create_foreign_key("fk_inventory_balance_tenant_product", "inventory_balances", "products", ["tenant_id", "product_id"], ["tenant_id", "id"])
    op.create_check_constraint("ck_inventory_balance_version_positive", "inventory_balances", "version >= 1")
    op.create_index("ix_inventory_balance_tenant_updated", "inventory_balances", ["tenant_id", "updated_at"])

    op.create_table(
        "inventory_movements",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("tenant_id", uuid, nullable=False),
        sa.Column("product_id", uuid, nullable=False),
        sa.Column("movement_type", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Numeric(), nullable=False),
        sa.Column("on_hand_delta", sa.Numeric(), nullable=False),
        sa.Column("reserved_delta", sa.Numeric(), nullable=False),
        sa.Column("on_hand_before", sa.Numeric(), nullable=False),
        sa.Column("on_hand_after", sa.Numeric(), nullable=False),
        sa.Column("reserved_before", sa.Numeric(), nullable=False),
        sa.Column("reserved_after", sa.Numeric(), nullable=False),
        sa.Column("reference_type", sa.String(64), nullable=True),
        sa.Column("reference_id", uuid, nullable=True),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("actor_type", sa.String(32), nullable=False),
        sa.Column("actor_id", uuid, nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("created_at", timestamp, nullable=False),
        sa.ForeignKeyConstraint(["tenant_id", "product_id"], ["products.tenant_id", "products.id"], name="fk_inventory_movement_tenant_product"),
        sa.CheckConstraint("movement_type IN ('OPENING_BALANCE','RECEIPT','POSITIVE_CORRECTION','NEGATIVE_CORRECTION','DAMAGE','WASTAGE','RESERVATION','RELEASE','CONSUMPTION')", name="ck_inventory_movement_type"),
        sa.CheckConstraint("quantity > 0 OR (movement_type='OPENING_BALANCE' AND quantity=0)", name="ck_inventory_movement_quantity"),
        sa.CheckConstraint("on_hand_after >= 0 AND reserved_after >= 0 AND reserved_after <= on_hand_after", name="ck_inventory_movement_after"),
    )
    op.create_index("ix_inventory_movements_product_cursor", "inventory_movements", ["tenant_id", "product_id", sa.text("created_at DESC"), sa.text("id DESC")])
    op.create_index("ix_inventory_movements_type_cursor", "inventory_movements", ["tenant_id", "movement_type", sa.text("created_at DESC")])
    op.create_index("uq_inventory_movements_staff_key", "inventory_movements", ["tenant_id", "actor_id", "idempotency_key"], unique=True, postgresql_where=sa.text("actor_id IS NOT NULL AND idempotency_key IS NOT NULL"))
    op.create_index("uq_inventory_movements_source", "inventory_movements", ["tenant_id", "movement_type", "reference_type", "reference_id"], unique=True, postgresql_where=sa.text("reference_id IS NOT NULL"))

    op.create_table(
        "catalog_change_history",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("tenant_id", uuid, nullable=False),
        sa.Column("product_id", uuid, nullable=False),
        sa.Column("change_type", sa.Text(), nullable=False),
        sa.Column("from_version", sa.Integer(), nullable=True),
        sa.Column("to_version", sa.Integer(), nullable=False),
        sa.Column("changes", postgresql.JSONB(), nullable=False),
        sa.Column("actor_id", uuid, sa.ForeignKey("staff_accounts.id"), nullable=False),
        sa.Column("created_at", timestamp, nullable=False),
        sa.ForeignKeyConstraint(["tenant_id", "product_id"], ["products.tenant_id", "products.id"], name="fk_catalog_history_tenant_product"),
        sa.CheckConstraint("change_type IN ('CREATED','UPDATED','ACTIVATED','DEACTIVATED')", name="ck_catalog_history_type"),
        sa.CheckConstraint("to_version >= 1", name="ck_catalog_history_version"),
    )
    op.create_index("ix_catalog_history_product", "catalog_change_history", ["tenant_id", "product_id", sa.text("created_at DESC")])

    op.execute("""
        INSERT INTO inventory_movements (
          id,tenant_id,product_id,movement_type,quantity,on_hand_delta,reserved_delta,
          on_hand_before,on_hand_after,reserved_before,reserved_after,reference_type,
          reference_id,reason,actor_type,created_at
        ) SELECT gen_random_uuid(),tenant_id,product_id,'OPENING_BALANCE',on_hand_quantity,
          on_hand_quantity,reserved_quantity,0,on_hand_quantity,0,reserved_quantity,
          'MIGRATION',product_id,
          'Migration opening balance','SYSTEM',now()
        FROM inventory_balances
    """)


def downgrade() -> None:
    op.execute("""
      DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM inventory_movements WHERE movement_type <> 'OPENING_BALANCE')
           OR EXISTS (SELECT 1 FROM catalog_change_history) THEN
          RAISE EXCEPTION 'catalog/inventory administration downgrade requires restore';
        END IF;
      END $$
    """)
    op.add_column("products", sa.Column("available", sa.Boolean(), nullable=True))
    op.execute("UPDATE products SET available=(status='ACTIVE')")
    op.alter_column("products", "available", nullable=False)
    op.drop_table("catalog_change_history")
    op.drop_table("inventory_movements")
    op.drop_index("ix_inventory_balance_tenant_updated", table_name="inventory_balances")
    op.drop_constraint("ck_inventory_balance_version_positive", "inventory_balances", type_="check")
    op.drop_constraint("fk_inventory_balance_tenant_product", "inventory_balances", type_="foreignkey")
    op.drop_constraint("uq_inventory_balance_tenant_product", "inventory_balances", type_="unique")
    op.drop_column("inventory_balances", "version")
    op.drop_column("inventory_balances", "tenant_id")
    op.drop_index("ix_products_admin_list", table_name="products")
    op.drop_constraint("uq_products_tenant_sku_normalized", "products", type_="unique")
    for name in ("ck_products_status", "ck_products_price_nonnegative", "ck_products_threshold_nonnegative", "ck_products_display_order_nonnegative", "ck_products_version_positive"):
        op.drop_constraint(name, "products", type_="check")
    op.drop_column("products", "version")
    op.drop_column("products", "low_stock_threshold")
    op.drop_column("products", "sku_normalized")
    op.drop_column("products", "status")

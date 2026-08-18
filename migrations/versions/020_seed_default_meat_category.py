"""seed Meat category for the default tenant

Revision ID: 020_seed_default_meat_category
Revises: 019_category_customer_visibility
"""

from collections.abc import Sequence

from alembic import op

revision: str = "020_seed_default_meat_category"
down_revision: str | None = "019_category_customer_visibility"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO product_categories (
            id,
            tenant_id,
            name,
            description,
            display_order,
            active,
            customer_visible
        )
        VALUES (
            '00000000-0000-0000-0001-000000000001'::uuid,
            '00000000-0000-0000-0000-000000000001'::uuid,
            'Meat',
            'Meat products',
            0,
            TRUE,
            TRUE
        )
        ON CONFLICT (tenant_id, name) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM product_categories
        WHERE id = '00000000-0000-0000-0001-000000000001'::uuid
          AND tenant_id = '00000000-0000-0000-0000-000000000001'::uuid
          AND name = 'Meat'
        """
    )

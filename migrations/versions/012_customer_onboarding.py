"""extend saved delivery profiles for customer onboarding

Revision ID: 012_customer_onboarding
Revises: 011_customer_web_chat
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "012_customer_onboarding"
down_revision: str | None = "011_customer_web_chat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "saved_delivery_profiles",
        sa.Column(
            "phone_verified", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "saved_delivery_profiles",
        sa.Column(
            "onboarding_status", sa.Text(), nullable=False, server_default="INCOMPLETE"
        ),
    )
    op.add_column(
        "saved_delivery_profiles", sa.Column("profile_consent_version", sa.Text())
    )
    op.add_column(
        "saved_delivery_profiles",
        sa.Column("profile_consented_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "saved_delivery_profiles", sa.Column("onboarding_request_id", sa.Text())
    )
    op.create_check_constraint(
        "ck_saved_profile_onboarding_status",
        "saved_delivery_profiles",
        "onboarding_status IN ('INCOMPLETE', 'COMPLETED')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_saved_profile_onboarding_status",
        "saved_delivery_profiles",
        type_="check",
    )
    op.drop_column("saved_delivery_profiles", "onboarding_request_id")
    op.drop_column("saved_delivery_profiles", "profile_consented_at")
    op.drop_column("saved_delivery_profiles", "profile_consent_version")
    op.drop_column("saved_delivery_profiles", "onboarding_status")
    op.drop_column("saved_delivery_profiles", "phone_verified")

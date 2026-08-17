from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from commerce.models import (
    AdminProduct,
    InventoryBalance,
    ManualInventoryMovementType,
    Product,
    ProductStatus,
)
from services.staff_catalog import CreateProductCommand, normalize_sku


def test_product_status_is_canonical_with_legacy_constructor_compatibility() -> None:
    inactive = Product(
        id=uuid4(), name="Chicken", price=Decimal(10), unit="kg", available=False
    )
    assert inactive.status == ProductStatus.INACTIVE
    assert inactive.available is False
    assert "available" not in inactive.model_dump()


def test_sku_normalization_preserves_display_and_normalizes_identity() -> None:
    display, normalized = normalize_sku("  ChK-  001  ")
    assert display == "ChK- 001"
    assert normalized == "chk- 001"


def test_manual_inventory_enum_cannot_represent_system_movements() -> None:
    with pytest.raises(ValueError):
        ManualInventoryMovementType("RESERVATION")


def test_inventory_balance_rejects_reserved_above_on_hand() -> None:
    with pytest.raises(ValidationError):
        InventoryBalance(
            product_id=uuid4(), tenant_id=uuid4(), on_hand_quantity=Decimal(1),
            reserved_quantity=Decimal(2), updated_at=datetime.now(timezone.utc),
        )


def test_create_command_defaults_inactive_and_accepts_zero_price() -> None:
    command = CreateProductCommand(
        sku="SKU-1", name="Sample", price=Decimal(0), currency="INR", unit="piece"
    )
    assert command.status == ProductStatus.INACTIVE


def test_admin_product_rejects_negative_threshold() -> None:
    with pytest.raises(ValidationError):
        AdminProduct(
            id=uuid4(), tenant_id=uuid4(), sku="SKU", name="Sample",
            category_id=None, price=Decimal(1), currency="INR", unit="piece",
            status=ProductStatus.ACTIVE, low_stock_threshold=Decimal(-1),
            display_order=0, version=1, created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

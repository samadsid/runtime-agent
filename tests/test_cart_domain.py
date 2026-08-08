from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from commerce.models import CartItem, CommerceSession, Product
from commerce.services import CartService


def product(name: str) -> Product:
    return Product(
        id=uuid4(),
        name=name,
        price=Decimal("10.00"),
        unit="kg",
    )


@pytest.mark.parametrize(
    "quantity",
    [Decimal(0), Decimal(-1), Decimal("NaN"), Decimal("Infinity")],
)
def test_cart_item_rejects_non_positive_or_non_finite_quantity(
    quantity: Decimal,
) -> None:
    with pytest.raises(ValidationError):
        CartItem(product=product("Chicken"), quantity=quantity)


def test_cart_service_adds_and_replaces_by_product_id_in_place() -> None:
    chicken = product("Chicken")
    rice = product("Rice")
    session = CommerceSession(
        selected_product=chicken,
        cart_items=(CartItem(product=rice, quantity=Decimal(1)),),
    )
    service = CartService()

    added = service.add_or_replace(session, chicken, Decimal(2))
    updated = service.add_or_replace(added, chicken, Decimal("3.5"))

    assert session.cart_items == (CartItem(product=rice, quantity=Decimal(1)),)
    assert tuple(item.product for item in updated.cart_items) == (rice, chicken)
    assert updated.cart_items[1].quantity == Decimal("3.5")
    assert updated.selected_product == chicken


def test_cart_service_removes_item_and_preserves_other_session_state() -> None:
    first = product("First")
    second = product("Second")
    session = CommerceSession(
        recent_product_results=(first, second),
        selected_product=second,
        cart_items=(
            CartItem(product=first, quantity=Decimal(1)),
            CartItem(product=second, quantity=Decimal(2)),
        ),
    )

    updated = CartService().remove(session, 0)

    assert updated.cart_items == (
        CartItem(product=second, quantity=Decimal(2)),
    )
    assert updated.recent_product_results == session.recent_product_results
    assert updated.selected_product == second

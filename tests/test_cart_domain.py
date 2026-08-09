from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from commerce.models import CartItem, CommerceSession, Product
from commerce.services import CartService
from tests.fakes import InMemoryCartRepository


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


@pytest.mark.asyncio
async def test_cart_service_adds_and_replaces_by_product_id_in_place() -> None:
    chicken = product("Chicken")
    rice = product("Rice")
    session = CommerceSession(
        selected_product=chicken,
        cart_items=(CartItem(product=rice, quantity=Decimal(1)),),
    )
    service = CartService(
        InMemoryCartRepository(products=(chicken, rice), items=session.cart_items)
    )

    await service.add_or_replace(UUID(int=0), UUID(int=0), chicken, Decimal(2))
    updated = await service.add_or_replace(
        UUID(int=0), UUID(int=0), chicken, Decimal("3.5")
    )

    assert tuple(item.product for item in updated.items) == (rice, chicken)
    assert updated.items[1].quantity == Decimal("3.5")


@pytest.mark.asyncio
async def test_cart_service_removes_item() -> None:
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

    repository = InMemoryCartRepository(items=session.cart_items)
    service = CartService(repository)
    cart = await service.get_active(UUID(int=0), UUID(int=0))
    assert cart is not None
    updated = await service.remove_by_ordinal(cart.id, 1)

    assert updated.items == (
        CartItem(product=second, quantity=Decimal(2)),
    )

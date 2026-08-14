from decimal import Decimal
from uuid import uuid4

import pytest

from commerce.models import CartItem, CommerceSession, Product
from commerce.services import CartService
from runtime.capabilities import CapabilityInput
from runtime.capabilities.add_to_cart import AddToCartCapability
from runtime.capabilities.remove_from_cart import RemoveFromCartCapability
from runtime.capabilities.view_cart import ViewCartCapability
from runtime.contracts import ExecutionStatus, ResponseFragmentKind
from tests.fakes import InMemoryCartRepository


def cart_service(
    products: tuple[Product, ...] = (), items: tuple[CartItem, ...] = ()
) -> CartService:
    return CartService(InMemoryCartRepository(products=products, items=items))


def product(name: str, unit: str = "kg") -> Product:
    return Product(
        id=uuid4(),
        name=name,
        price=Decimal("10.00"),
        unit=unit,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("quantity", [2, 2.5, "2.75", Decimal("3.25")])
async def test_add_to_cart_adds_selected_product_with_valid_quantity(quantity) -> None:
    chicken = product("Chicken Breast")
    session = CommerceSession(selected_product=chicken)

    output = await AddToCartCapability(cart_service((chicken,))).execute(
        CapabilityInput[CommerceSession](
            data={"quantity": quantity},
            session=session,
        )
    )

    assert output.outcome.status == ExecutionStatus.SUCCESS
    assert output.outcome.follow_up is not None
    assert output.outcome.follow_up.id == "confirm-cart-order"
    assert output.session.cart_items[0].product == chicken
    assert output.session.cart_items[0].quantity == Decimal(str(quantity))
    assert chicken.name in output.outcome.fragments[0].text
    assert chicken.unit in output.outcome.fragments[0].text
    assert output.session.checkout.stage.value == "REVIEWING_CART"
    assert output.outcome.fragments[1].text == "Checkout cart review:"
    assert "Chicken Breast" in output.outcome.fragments[2].text


@pytest.mark.asyncio
async def test_add_to_cart_uses_sole_recent_result_when_product_is_not_selected() -> None:
    chicken = product("Chicken Breast")
    session = CommerceSession(recent_product_results=(chicken,))

    output = await AddToCartCapability(cart_service(products=(chicken,))).execute(
        CapabilityInput[CommerceSession](data={"quantity": 1}, session=session)
    )

    assert output.outcome.status == ExecutionStatus.SUCCESS
    assert output.session.selected_product == chicken
    assert output.session.cart_items[0].product == chicken
    assert output.session.cart_items[0].quantity == Decimal(1)
    assert "Added 1 kg Chicken Breast" in output.outcome.fragments[0].text


@pytest.mark.asyncio
async def test_add_to_cart_does_not_guess_between_multiple_recent_results() -> None:
    breast = product("Chicken Breast")
    wings = product("Chicken Wings")
    session = CommerceSession(recent_product_results=(breast, wings))

    output = await AddToCartCapability(
        cart_service(products=(breast, wings))
    ).execute(CapabilityInput[CommerceSession](data={"quantity": 1}, session=session))

    assert output.outcome.status == ExecutionStatus.MISSING_INPUT
    assert output.session == session
    assert output.outcome.follow_up.id == "select-product-for-cart"


@pytest.mark.asyncio
async def test_add_to_cart_replaces_existing_quantity_without_reordering() -> None:
    rice = product("Rice")
    chicken = product("Chicken Breast")
    session = CommerceSession(
        selected_product=chicken,
        cart_items=(
            CartItem(product=rice, quantity=Decimal(1)),
            CartItem(product=chicken, quantity=Decimal(2)),
        ),
    )

    output = await AddToCartCapability(cart_service(items=session.cart_items)).execute(
        CapabilityInput[CommerceSession](
            data={"quantity": "4"},
            session=session,
        )
    )

    assert tuple(item.product for item in output.session.cart_items) == (rice, chicken)
    assert output.session.cart_items[1].quantity == Decimal(4)
    assert output.session.selected_product == chicken


@pytest.mark.asyncio
async def test_add_to_cart_without_product_context_requests_search() -> None:
    session = CommerceSession()

    output = await AddToCartCapability(cart_service()).execute(
        CapabilityInput[CommerceSession](data={"quantity": 2}, session=session)
    )

    assert output.session == session
    assert output.outcome.status == ExecutionStatus.MISSING_INPUT
    assert output.outcome.follow_up is not None
    assert output.outcome.follow_up.options == ()
    assert "search" in output.outcome.follow_up.question.lower()


@pytest.mark.asyncio
async def test_add_to_cart_rejects_missing_quantity_without_mutation() -> None:
    chicken = product("Chicken")
    session = CommerceSession(selected_product=chicken)

    output = await AddToCartCapability(cart_service()).execute(
        CapabilityInput[CommerceSession](data={}, session=session)
    )

    assert output.session == session
    assert output.outcome.status == ExecutionStatus.MISSING_INPUT
    assert output.outcome.follow_up is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "quantity",
    [None, "invalid", 0, -1, True, float("nan"), float("inf")],
)
async def test_add_to_cart_rejects_invalid_quantity_without_mutation(quantity) -> None:
    chicken = product("Chicken")
    existing = CartItem(product=chicken, quantity=Decimal(1))
    session = CommerceSession(selected_product=chicken, cart_items=(existing,))

    output = await AddToCartCapability(cart_service()).execute(
        CapabilityInput[CommerceSession](
            data={"quantity": quantity},
            session=session,
        )
    )

    assert output.session == session
    assert output.outcome.status == ExecutionStatus.INVALID_INPUT
    assert output.outcome.follow_up is not None
    assert output.session.cart_items == (existing,)


@pytest.mark.asyncio
async def test_view_cart_returns_empty_cart_follow_up() -> None:
    session = CommerceSession()

    output = await ViewCartCapability(cart_service()).execute(
        CapabilityInput[CommerceSession](session=session)
    )

    assert output.session == session
    assert output.outcome.status == ExecutionStatus.NOT_FOUND
    assert output.outcome.follow_up is not None
    assert output.outcome.fragments[0].text == "Your cart is empty."


@pytest.mark.asyncio
async def test_view_cart_returns_ordered_items_without_prices_or_totals() -> None:
    chicken = product("Chicken", "kg")
    juice = product("Juice", "bottle")
    session = CommerceSession(
        cart_items=(
            CartItem(product=chicken, quantity=Decimal(2)),
            CartItem(product=juice, quantity=Decimal(3)),
        )
    )

    output = await ViewCartCapability(cart_service(items=session.cart_items)).execute(
        CapabilityInput[CommerceSession](session=session)
    )

    texts = tuple(fragment.text for fragment in output.outcome.fragments)
    assert texts == (
        "Your cart:",
        "1. Chicken — 2 kg",
        "2. Juice — 3 bottle",
    )
    assert output.outcome.fragments[1].kind == ResponseFragmentKind.ITEM
    assert "₹" not in " ".join(texts)
    assert "total" not in " ".join(texts).lower()


@pytest.mark.asyncio
async def test_remove_from_cart_removes_valid_ordinal_only() -> None:
    chicken = product("Chicken")
    rice = product("Rice")
    session = CommerceSession(
        selected_product=chicken,
        cart_items=(
            CartItem(product=chicken, quantity=Decimal(2)),
            CartItem(product=rice, quantity=Decimal(1)),
        ),
    )

    output = await RemoveFromCartCapability(cart_service(items=session.cart_items)).execute(
        CapabilityInput[CommerceSession](data={"ordinal": 1}, session=session)
    )

    assert output.outcome.status == ExecutionStatus.SUCCESS
    assert tuple(item.product for item in output.session.cart_items) == (rice,)
    assert output.session.selected_product == chicken
    assert "Chicken" in output.outcome.fragments[0].text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("arguments", "status"),
    [
        ({}, ExecutionStatus.MISSING_INPUT),
        ({"ordinal": 0}, ExecutionStatus.INVALID_INPUT),
        ({"ordinal": -1}, ExecutionStatus.INVALID_INPUT),
        ({"ordinal": 3}, ExecutionStatus.INVALID_INPUT),
        ({"ordinal": "1"}, ExecutionStatus.INVALID_INPUT),
        ({"ordinal": True}, ExecutionStatus.INVALID_INPUT),
    ],
)
async def test_remove_from_cart_rejects_missing_or_invalid_ordinal(
    arguments: dict[str, object],
    status: ExecutionStatus,
) -> None:
    chicken = product("Chicken")
    session = CommerceSession(
        cart_items=(CartItem(product=chicken, quantity=Decimal(2)),)
    )

    output = await RemoveFromCartCapability(cart_service(items=session.cart_items)).execute(
        CapabilityInput[CommerceSession](data=arguments, session=session)
    )

    assert output.session == session
    assert output.outcome.status == status
    assert output.outcome.follow_up is not None
    assert tuple(option.label for option in output.outcome.follow_up.options) == (
        "1. Chicken",
    )


@pytest.mark.asyncio
async def test_remove_from_empty_cart_requests_product_search() -> None:
    session = CommerceSession()

    output = await RemoveFromCartCapability(cart_service()).execute(
        CapabilityInput[CommerceSession](data={"ordinal": 1}, session=session)
    )

    assert output.session == session
    assert output.outcome.status == ExecutionStatus.NOT_FOUND
    assert output.outcome.follow_up is not None
    assert "search" in output.outcome.follow_up.question.lower()


@pytest.mark.asyncio
async def test_add_to_cart_does_not_return_success_when_persistence_fails() -> None:
    chicken = product("Chicken")
    repository = InMemoryCartRepository(products=(chicken,))
    repository.fail_writes = True
    capability = AddToCartCapability(CartService(repository))

    with pytest.raises(RuntimeError, match="persistence failed"):
        await capability.execute(
            CapabilityInput[CommerceSession](
                data={"quantity": 2},
                session=CommerceSession(selected_product=chicken),
            )
        )

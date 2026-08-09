from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from commerce.models import (
    CartItem,
    CheckoutStage,
    CheckoutState,
    CommerceSession,
    PendingCartClear,
    Product,
)
from commerce.services import CartService
from runtime.capabilities import CapabilityInput, ExecutionContext
from runtime.capabilities.add_to_cart import AddToCartCapability
from runtime.capabilities.clear_cart import ClearCartCapability
from runtime.capabilities.remove_from_cart import RemoveFromCartCapability
from runtime.capabilities.update_cart_item_quantity import (
    UpdateCartItemQuantityCapability,
)
from runtime.contracts import ExecutionStatus
from tests.fakes import InMemoryCartRepository


def product(name: str = "Chicken Breast") -> Product:
    return Product(
        id=uuid4(),
        name=name,
        price=Decimal("320.00"),
        unit="kg",
    )


def capability_input(
    session: CommerceSession, data: dict[str, object]
) -> CapabilityInput[CommerceSession]:
    return CapabilityInput(
        data=data,
        session=session,
        context=ExecutionContext(tenant_id=UUID(int=0), conversation_id=UUID(int=0)),
    )


@pytest.mark.asyncio
async def test_quantity_update_persists_refreshes_and_invalidates_checkout() -> None:
    item = CartItem(product=product(), quantity=Decimal(2))
    repository = InMemoryCartRepository(items=(item,))
    cart = next(iter(repository.carts.values()))
    session = CommerceSession(
        cart_items=(item,),
        checkout=CheckoutState(
            stage=CheckoutStage.READY_TO_CONFIRM,
            source_cart_id=cart.id,
            customer_name="Samad",
            phone_number="999",
            delivery_address="Market Road",
        ),
        pending_cart_clear=PendingCartClear(
            cart_id=cart.id,
            cart_version=cart.version,
            requested_at=datetime.now(timezone.utc),
        ),
    )

    output = await UpdateCartItemQuantityCapability(
        CartService(repository)
    ).execute(capability_input(session, {"ordinal": 1, "quantity": "3.5"}))

    persisted = next(iter(repository.carts.values()))
    assert persisted.items[0].quantity == Decimal("3.5")
    assert persisted.version == 1
    assert output.session.cart_items == persisted.items
    assert output.session.checkout == CheckoutState()
    assert output.session.pending_cart_clear is None
    assert output.outcome.status == ExecutionStatus.SUCCESS
    assert output.outcome.protected_values == ("Chicken Breast", "3.5", "kg")


@pytest.mark.asyncio
async def test_same_quantity_update_is_idempotent() -> None:
    item = CartItem(product=product(), quantity=Decimal(2))
    repository = InMemoryCartRepository(items=(item,))
    cart = next(iter(repository.carts.values()))
    checkout = CheckoutState(
        stage=CheckoutStage.REVIEWING_CART,
        source_cart_id=cart.id,
    )
    session = CommerceSession(cart_items=(item,), checkout=checkout)

    output = await UpdateCartItemQuantityCapability(
        CartService(repository)
    ).execute(capability_input(session, {"ordinal": 1, "quantity": 2}))

    assert next(iter(repository.carts.values())).version == 0
    assert output.session.checkout == checkout


@pytest.mark.asyncio
@pytest.mark.parametrize("quantity", [None, 0, -1, "NaN", "Infinity", "bad"])
async def test_invalid_quantities_do_not_mutate(quantity: object) -> None:
    item = CartItem(product=product(), quantity=Decimal(2))
    repository = InMemoryCartRepository(items=(item,))
    data: dict[str, object] = {"ordinal": 1}
    if quantity is not None:
        data["quantity"] = quantity

    output = await UpdateCartItemQuantityCapability(
        CartService(repository)
    ).execute(capability_input(CommerceSession(cart_items=(item,)), data))

    persisted = next(iter(repository.carts.values()))
    assert persisted.items == (item,)
    assert persisted.version == 0
    assert output.outcome.status in {
        ExecutionStatus.MISSING_INPUT,
        ExecutionStatus.INVALID_INPUT,
    }


@pytest.mark.asyncio
async def test_invalid_update_target_returns_current_cart_options() -> None:
    items = (
        CartItem(product=product("Chicken Breast"), quantity=Decimal(2)),
        CartItem(product=product("Chicken Wings"), quantity=Decimal(1)),
    )
    repository = InMemoryCartRepository(items=items)

    output = await UpdateCartItemQuantityCapability(
        CartService(repository)
    ).execute(capability_input(CommerceSession(), {"quantity": 3}))

    assert output.outcome.status == ExecutionStatus.MISSING_INPUT
    assert output.outcome.follow_up is not None
    assert tuple(option.label for option in output.outcome.follow_up.options) == (
        "1. Chicken Breast",
        "2. Chicken Wings",
    )


@pytest.mark.asyncio
async def test_clear_review_decline_and_confirmation_flow() -> None:
    item = CartItem(product=product(), quantity=Decimal(2))
    repository = InMemoryCartRepository(items=(item,))
    capability = ClearCartCapability(
        CartService(repository),
        clock=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    review = await capability.execute(capability_input(CommerceSession(), {}))
    persisted = next(iter(repository.carts.values()))
    assert persisted.items == (item,)
    assert persisted.version == 0
    assert review.session.pending_cart_clear is not None
    assert review.session.pending_cart_clear.cart_version == 0
    assert review.outcome.follow_up is not None

    declined = await capability.execute(
        capability_input(review.session, {"declined": True})
    )
    assert declined.session.pending_cart_clear is None
    assert next(iter(repository.carts.values())).items == (item,)

    second_review = await capability.execute(
        capability_input(declined.session, {"confirmed": False})
    )
    confirmed = await capability.execute(
        capability_input(second_review.session, {"confirmed": True})
    )
    persisted = next(iter(repository.carts.values()))
    assert persisted.items == ()
    assert persisted.version == 1
    assert confirmed.session.cart_items == ()
    assert confirmed.session.pending_cart_clear is None
    assert confirmed.session.checkout == CheckoutState()


@pytest.mark.asyncio
async def test_stale_confirmation_preserves_items_and_creates_fresh_review() -> None:
    item = CartItem(product=product(), quantity=Decimal(2))
    repository = InMemoryCartRepository(items=(item,))
    capability = ClearCartCapability(CartService(repository))
    review = await capability.execute(capability_input(CommerceSession(), {}))
    assert review.session.pending_cart_clear is not None

    await repository.update_item_quantity_by_ordinal(
        UUID(int=0), UUID(int=0), 1, Decimal(3)
    )
    stale = await capability.execute(
        capability_input(review.session, {"confirmed": True})
    )

    persisted = next(iter(repository.carts.values()))
    assert persisted.items[0].quantity == Decimal(3)
    assert stale.session.pending_cart_clear is not None
    assert stale.session.pending_cart_clear.cart_version == persisted.version
    assert stale.outcome.fragments[0].id == "stale-cart-clear"
    assert stale.outcome.follow_up is not None


@pytest.mark.asyncio
async def test_repeated_confirmation_without_pending_never_clears_later_cart() -> None:
    item = CartItem(product=product(), quantity=Decimal(2))
    repository = InMemoryCartRepository(items=(item,))
    capability = ClearCartCapability(CartService(repository))
    review = await capability.execute(capability_input(CommerceSession(), {}))
    cleared = await capability.execute(
        capability_input(review.session, {"confirmed": True})
    )
    await repository.add_or_replace_item(
        next(iter(repository.carts.values())).id,
        item.product.id,
        Decimal(4),
    )

    repeated = await capability.execute(
        capability_input(cleared.session, {"confirmed": True})
    )

    assert next(iter(repository.carts.values())).items[0].quantity == Decimal(4)
    assert repeated.outcome.status == ExecutionStatus.MISSING_INPUT


@pytest.mark.asyncio
async def test_cart_edit_persistence_failure_keeps_session_and_items() -> None:
    item = CartItem(product=product(), quantity=Decimal(2))
    repository = InMemoryCartRepository(items=(item,))
    repository.fail_writes = True
    session = CommerceSession(cart_items=(item,))

    output = await UpdateCartItemQuantityCapability(
        CartService(repository)
    ).execute(capability_input(session, {"ordinal": 1, "quantity": 3}))

    assert output.outcome.status == ExecutionStatus.FAILURE
    assert output.session == session
    assert next(iter(repository.carts.values())).items == (item,)


@pytest.mark.asyncio
async def test_clear_persistence_failure_keeps_pending_review_and_items() -> None:
    item = CartItem(product=product(), quantity=Decimal(2))
    repository = InMemoryCartRepository(items=(item,))
    capability = ClearCartCapability(CartService(repository))
    review = await capability.execute(capability_input(CommerceSession(), {}))
    repository.fail_writes = True

    output = await capability.execute(
        capability_input(review.session, {"confirmed": True})
    )

    assert output.outcome.status == ExecutionStatus.FAILURE
    assert output.session == review.session
    assert next(iter(repository.carts.values())).items == (item,)


@pytest.mark.asyncio
async def test_existing_add_and_remove_mutations_increment_version_and_reset_workflows() -> None:
    chicken = product()
    item = CartItem(product=chicken, quantity=Decimal(2))
    repository = InMemoryCartRepository(products=(chicken,), items=(item,))
    cart = next(iter(repository.carts.values()))
    pending = PendingCartClear(
        cart_id=cart.id,
        cart_version=cart.version,
        requested_at=datetime.now(timezone.utc),
    )
    checkout = CheckoutState(
        stage=CheckoutStage.REVIEWING_CART,
        source_cart_id=cart.id,
    )

    added = await AddToCartCapability(CartService(repository)).execute(
        capability_input(
            CommerceSession(
                selected_product=chicken,
                cart_items=(item,),
                checkout=checkout,
                pending_cart_clear=pending,
            ),
            {"quantity": 3},
        )
    )
    assert next(iter(repository.carts.values())).version == 1
    assert added.session.checkout == CheckoutState()
    assert added.session.pending_cart_clear is None

    refreshed = next(iter(repository.carts.values()))
    removed = await RemoveFromCartCapability(CartService(repository)).execute(
        capability_input(
            added.session.model_copy(
                update={
                    "checkout": checkout,
                    "pending_cart_clear": PendingCartClear(
                        cart_id=refreshed.id,
                        cart_version=refreshed.version,
                        requested_at=datetime.now(timezone.utc),
                    ),
                }
            ),
            {"ordinal": 1},
        )
    )
    assert next(iter(repository.carts.values())).version == 2
    assert removed.session.checkout == CheckoutState()
    assert removed.session.pending_cart_clear is None

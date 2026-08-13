from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from commerce.models import (
    CommerceSession,
    PendingCartAddition,
    PendingCartProductOption,
    Product,
)
from commerce.repositories import InMemoryProductRepository
from commerce.services import DirectCartService
from runtime.capabilities import CapabilityInput, ExecutionContext
from runtime.capabilities.add_product_to_cart import AddProductToCartCapability
from runtime.capabilities.select_product_for_pending_cart_addition import (
    SelectProductForPendingCartAdditionCapability,
)
from runtime.contracts import ExecutionStatus
from tests.fakes import InMemoryCartRepository


def context(request_id: str = "request-1") -> ExecutionContext:
    return ExecutionContext(
        tenant_id=UUID(int=1), conversation_id=UUID(int=2), request_id=request_id
    )


def product(name: str, unit: str = "kg", available: bool = True) -> Product:
    return Product(
        id=uuid4(), name=name, price=Decimal(100), unit=unit, available=available
    )


def capability(products: list[Product]):
    carts = InMemoryCartRepository(tuple(products))
    service = DirectCartService(InMemoryProductRepository(products), carts)
    return AddProductToCartCapability(service), service, carts


@pytest.mark.asyncio
async def test_unique_direct_add_uses_canonical_unit_and_updates_session() -> None:
    chicken = product("Chicken Breast")
    direct, _, _ = capability([chicken])
    output = await direct.execute(
        CapabilityInput(
            data={
                "product_query": " chicken breast ",
                "quantity": 10,
                "stated_unit": "kilos",
            },
            session=CommerceSession(),
            context=context(),
        )
    )
    assert output.outcome.status is ExecutionStatus.SUCCESS
    assert output.session.selected_product == chicken
    assert output.session.cart_items[0].quantity == Decimal(10)
    assert output.outcome.fragments[0].id == "direct-cart-item-added"


@pytest.mark.asyncio
async def test_resolution_tolerates_quantity_and_unit_leaking_into_query() -> None:
    chicken = product("Chicken Breast")
    direct, _, _ = capability([chicken])
    output = await direct.execute(
        CapabilityInput(
            data={
                "product_query": "chicken breast 10 kg",
                "quantity": 10,
                "stated_unit": "kg",
            },
            session=CommerceSession(),
            context=context(),
        )
    )
    assert output.outcome.status is ExecutionStatus.SUCCESS
    assert output.session.selected_product == chicken


@pytest.mark.asyncio
async def test_ambiguous_direct_add_preserves_pending_quantity_and_unit() -> None:
    direct, _, carts = capability([product("Chicken Breast"), product("Chicken Wings")])
    output = await direct.execute(
        CapabilityInput(
            data={"product_query": "chicken", "quantity": 5, "stated_unit": "kilo"},
            session=CommerceSession(),
            context=context(),
        )
    )
    assert output.outcome.status is ExecutionStatus.CONFLICT
    assert output.session.pending_cart_addition is not None
    assert output.session.pending_cart_addition.quantity == Decimal(5)
    assert output.session.pending_cart_addition.stated_unit == "kg"
    assert not carts.carts


@pytest.mark.asyncio
async def test_unit_mismatch_does_not_mutate_cart() -> None:
    direct, _, carts = capability([product("Nuggets", "pack")])
    output = await direct.execute(
        CapabilityInput(
            data={"product_query": "Nuggets", "quantity": 2, "stated_unit": "kg"},
            session=CommerceSession(),
            context=context(),
        )
    )
    assert output.outcome.fragments[0].id == "direct-cart-unit-mismatch"
    assert not carts.carts


@pytest.mark.asyncio
async def test_same_request_is_idempotent_without_version_increment() -> None:
    chicken = product("Chicken Breast")
    direct, _, _ = capability([chicken])
    request = CapabilityInput(
        data={"product_query": "Chicken Breast", "quantity": 2},
        session=CommerceSession(),
        context=context(),
    )
    first = await direct.execute(request)
    replay = await direct.execute(request.model_copy(update={"session": first.session}))
    assert replay.session.cart_items == first.session.cart_items


@pytest.mark.asyncio
async def test_pending_selection_uses_preserved_quantity_and_clears_state() -> None:
    breast = product("Chicken Breast")
    _, service, _ = capability([breast, product("Chicken Wings")])
    now = datetime.now(timezone.utc)
    pending = PendingCartAddition(
        options=(
            PendingCartProductOption(
                product_id=breast.id, display_name=breast.name, canonical_unit="kg"
            ),
        ),
        quantity=Decimal(5),
        stated_unit="kg",
        created_at=now,
        source_request_id="first",
    )
    selector = SelectProductForPendingCartAdditionCapability(service, clock=lambda: now)
    output = await selector.execute(
        CapabilityInput(
            data={"ordinal": 1},
            session=CommerceSession(pending_cart_addition=pending),
            context=context("second"),
        )
    )
    assert output.outcome.status is ExecutionStatus.SUCCESS
    assert output.session.pending_cart_addition is None
    assert output.session.cart_items[0].quantity == Decimal(5)


@pytest.mark.asyncio
async def test_pending_cancel_and_expiry_never_mutate_cart() -> None:
    breast = product("Chicken Breast")
    _, service, carts = capability([breast])
    created = datetime.now(timezone.utc)
    pending = PendingCartAddition(
        options=(
            PendingCartProductOption(
                product_id=breast.id, display_name=breast.name, canonical_unit="kg"
            ),
        ),
        quantity=Decimal(2),
        created_at=created,
        source_request_id="first",
    )
    cancelled = await SelectProductForPendingCartAdditionCapability(service).execute(
        CapabilityInput(
            data={"cancelled": True},
            session=CommerceSession(pending_cart_addition=pending),
            context=context(),
        )
    )
    assert cancelled.session.pending_cart_addition is None
    expired = await SelectProductForPendingCartAdditionCapability(
        service, clock=lambda: created + timedelta(minutes=16)
    ).execute(
        CapabilityInput(
            data={"ordinal": 1},
            session=CommerceSession(pending_cart_addition=pending),
            context=context(),
        )
    )
    assert expired.outcome.fragments[0].id == "pending-cart-addition-expired"
    assert not carts.carts

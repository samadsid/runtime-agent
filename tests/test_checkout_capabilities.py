from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from commerce.models import (
    CartItem,
    CheckoutStage,
    CheckoutState,
    CommerceSession,
    OrderStatus,
    Product,
    StockShortage,
)
from commerce.repositories import InsufficientStockError
from commerce.services import (
    CartService,
    NonEmptyPhoneValidationPolicy,
    OrderService,
)
from runtime.capabilities import CapabilityInput
from runtime.capabilities.checkout import CheckoutCapability
from runtime.capabilities.collect_delivery_details import (
    CollectDeliveryDetailsCapability,
)
from runtime.capabilities.confirm_order import ConfirmOrderCapability
from runtime.capabilities.get_order_status import GetOrderStatusCapability
from runtime.contracts import ExecutionStatus
from tests.fakes import InMemoryCartRepository, InMemoryOrderRepository


def product(name: str = "Chicken Breast") -> Product:
    return Product(id=uuid4(), name=name, price=Decimal("320.00"), unit="kg")


def input_for(
    session: CommerceSession, data: dict[str, object] | None = None
) -> CapabilityInput[CommerceSession]:
    return CapabilityInput[CommerceSession](data=data or {}, session=session)


@pytest.mark.asyncio
async def test_checkout_rejects_empty_persisted_cart() -> None:
    capability = CheckoutCapability(CartService(InMemoryCartRepository()))

    output = await capability.execute(input_for(CommerceSession()))

    assert output.outcome.status == ExecutionStatus.NOT_FOUND
    assert output.session.checkout.stage == CheckoutStage.NONE


@pytest.mark.asyncio
async def test_checkout_reviews_persisted_cart_then_advances_to_details() -> None:
    chicken = product()
    item = CartItem(product=chicken, quantity=Decimal(2))
    repository = InMemoryCartRepository(items=(item,))
    capability = CheckoutCapability(CartService(repository))

    review = await capability.execute(input_for(CommerceSession()))
    proceed = await capability.execute(input_for(review.session))

    assert review.session.checkout.stage == CheckoutStage.REVIEWING_CART
    assert review.session.checkout.source_cart_id is not None
    assert "Chicken Breast" in review.outcome.fragments[1].text
    assert "₹320.00" in review.outcome.fragments[1].text
    assert proceed.session.checkout.stage == CheckoutStage.COLLECTING_DETAILS
    assert proceed.outcome.follow_up is not None
    assert proceed.outcome.follow_up.id == "request-delivery-details"
    assert "name" in proceed.outcome.follow_up.question
    assert "phone number" in proceed.outcome.follow_up.question
    assert "delivery address" in proceed.outcome.follow_up.question


@pytest.mark.asyncio
async def test_delivery_details_ask_only_for_next_missing_field() -> None:
    capability = CollectDeliveryDetailsCapability(NonEmptyPhoneValidationPolicy())
    session = CommerceSession(
        checkout=CheckoutState(
            stage=CheckoutStage.COLLECTING_DETAILS,
            source_cart_id=uuid4(),
        )
    )

    named = await capability.execute(input_for(session, {"customer_name": " Samad "}))
    phoned = await capability.execute(
        input_for(named.session, {"phone_number": "9876543210"})
    )
    addressed = await capability.execute(
        input_for(phoned.session, {"delivery_address": " 12 Market Road "})
    )

    assert named.session.checkout.customer_name == "Samad"
    assert named.outcome.follow_up is not None
    assert named.outcome.follow_up.id == "request-phone-number"
    assert phoned.outcome.follow_up is not None
    assert phoned.outcome.follow_up.id == "request-delivery-address"
    assert addressed.session.checkout.stage == CheckoutStage.READY_TO_CONFIRM
    assert addressed.session.checkout.delivery_address == "12 Market Road"
    assert addressed.outcome.follow_up is not None
    assert addressed.outcome.follow_up.id == "confirm-order"


@pytest.mark.asyncio
async def test_delivery_details_accept_all_fields_in_one_reply() -> None:
    capability = CollectDeliveryDetailsCapability(NonEmptyPhoneValidationPolicy())
    session = CommerceSession(
        checkout=CheckoutState(
            stage=CheckoutStage.COLLECTING_DETAILS,
            source_cart_id=uuid4(),
        )
    )

    output = await capability.execute(
        input_for(
            session,
            {
                "customer_name": "Samad",
                "phone_number": "9560717170",
                "delivery_address": "B-68 2nd Floor DDA Colony New Zafrabad Delhi",
            },
        )
    )

    assert output.session.checkout.stage == CheckoutStage.READY_TO_CONFIRM
    assert output.outcome.follow_up is not None
    assert output.outcome.follow_up.id == "confirm-order"


@pytest.mark.asyncio
async def test_invalid_supplied_detail_asks_for_that_field() -> None:
    capability = CollectDeliveryDetailsCapability(NonEmptyPhoneValidationPolicy())
    session = CommerceSession(
        checkout=CheckoutState(
            stage=CheckoutStage.COLLECTING_DETAILS,
            source_cart_id=uuid4(),
        )
    )

    output = await capability.execute(input_for(session, {"phone_number": "   "}))

    assert output.outcome.status == ExecutionStatus.INVALID_INPUT
    assert output.outcome.follow_up is not None
    assert output.outcome.follow_up.question == (
        "What phone number should I use for delivery?"
    )


@pytest.mark.asyncio
async def test_confirmation_requires_complete_ready_checkout() -> None:
    repository = InMemoryOrderRepository(InMemoryCartRepository())
    capability = ConfirmOrderCapability(OrderService(repository))

    output = await capability.execute(input_for(CommerceSession(), {"confirmed": True}))

    assert output.outcome.status == ExecutionStatus.INVALID_INPUT
    assert repository.orders == []


@pytest.mark.asyncio
async def test_confirmation_clears_unavailable_checkout_cart() -> None:
    repository = InMemoryOrderRepository(InMemoryCartRepository())
    capability = ConfirmOrderCapability(OrderService(repository))
    session = CommerceSession(
        checkout=CheckoutState(
            stage=CheckoutStage.READY_TO_CONFIRM,
            source_cart_id=uuid4(),
            customer_name="Samad",
            phone_number="9876543210",
            delivery_address="12 Market Road",
        )
    )

    output = await capability.execute(input_for(session, {"confirmed": True}))

    assert output.outcome.status == ExecutionStatus.NOT_FOUND
    assert output.session.checkout == CheckoutState()


@pytest.mark.asyncio
async def test_confirmation_snapshots_cart_closes_it_and_is_idempotent() -> None:
    chicken = product()
    cart_repository = InMemoryCartRepository(
        items=(CartItem(product=chicken, quantity=Decimal("2.5")),)
    )
    cart = await cart_repository.get_active_cart(UUID(int=0), UUID(int=0))
    assert cart is not None
    order_repository = InMemoryOrderRepository(cart_repository)
    service = OrderService(order_repository)
    session = CommerceSession(
        cart_items=cart.items,
        checkout=CheckoutState(
            stage=CheckoutStage.READY_TO_CONFIRM,
            source_cart_id=cart.id,
            customer_name="Samad",
            phone_number="9876543210",
            delivery_address="12 Market Road",
        ),
    )

    output = await ConfirmOrderCapability(service).execute(
        input_for(session, {"confirmed": True})
    )
    first = order_repository.orders[0]
    retried = await service.create_confirmed_order_from_cart(
        UUID(int=0), cart.id, "Samad", "9876543210", "12 Market Road"
    )

    assert output.outcome.status == ExecutionStatus.SUCCESS
    assert output.session.cart_items == ()
    assert output.session.checkout == CheckoutState()
    assert first.id == retried.id
    assert len(order_repository.orders) == 1
    assert first.items[0].product_name == "Chicken Breast"
    assert first.items[0].unit_price == Decimal("320.00")
    assert first.items[0].quantity == Decimal("2.5")
    assert await cart_repository.get_active_cart(UUID(int=0), UUID(int=0)) is None


@pytest.mark.asyncio
async def test_confirmation_reports_only_grounded_stock_shortages() -> None:
    chicken = product()

    class InsufficientService:
        async def create_confirmed_order_from_cart(self, **kwargs):
            raise InsufficientStockError(
                (
                    StockShortage(
                        product_id=chicken.id,
                        product_name=chicken.name,
                        requested_quantity=Decimal("2.5"),
                        sellable_quantity=Decimal(1),
                        unit=chicken.unit,
                    ),
                )
            )

    session = CommerceSession(
        checkout=CheckoutState(
            stage=CheckoutStage.READY_TO_CONFIRM,
            source_cart_id=uuid4(),
            customer_name="Samad",
            phone_number="9876543210",
            delivery_address="12 Market Road",
        )
    )
    capability = ConfirmOrderCapability(InsufficientService())  # type: ignore[arg-type]

    output = await capability.execute(input_for(session, {"confirmed": True}))

    assert output.outcome.status == ExecutionStatus.FAILURE
    assert output.session == session
    assert output.outcome.fragments[0].text == (
        "Chicken Breast: requested 2.5 kg; currently sellable 1 kg."
    )
    assert output.outcome.protected_values == (
        "Chicken Breast",
        "2.5",
        "1",
        "kg",
    )


@pytest.mark.asyncio
async def test_get_order_status_returns_latest_persisted_status() -> None:
    chicken = product()
    cart_repository = InMemoryCartRepository(
        items=(CartItem(product=chicken, quantity=Decimal(1)),)
    )
    cart = await cart_repository.get_active_cart(UUID(int=0), UUID(int=0))
    assert cart is not None
    order_repository = InMemoryOrderRepository(cart_repository)
    service = OrderService(order_repository)
    order = await service.create_confirmed_order_from_cart(
        UUID(int=0), cart.id, "Samad", "9876543210", "12 Market Road"
    )

    output = await GetOrderStatusCapability(service).execute(
        input_for(CommerceSession())
    )

    assert output.outcome.status == ExecutionStatus.SUCCESS
    assert str(order.id) in output.outcome.fragments[0].text
    assert OrderStatus.CONFIRMED.value in output.outcome.fragments[0].text

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import TracebackType
from uuid import uuid4

import pytest

from commerce.models import (
    FulfilmentActor,
    FulfilmentActorType,
    InventoryBalance,
    InventoryReservation,
    InventoryReservationStatus,
    Order,
    OrderItem,
    OrderStatus,
    PaymentMethod,
)
from commerce.repositories import (
    FulfilmentUnitOfWork,
    InvalidOrderTransitionError,
    InventoryRepository,
    InventoryStateConflictError,
    OrderRepository,
)
from commerce.services import FulfilmentService
from tests.fakes import InMemoryCartRepository, InMemoryOrderRepository


def make_order(status: OrderStatus = OrderStatus.CONFIRMED) -> Order:
    order_id = uuid4()
    return Order(
        id=order_id,
        tenant_id=uuid4(),
        public_order_number="MU-260818-0001",
        source_cart_id=uuid4(),
        conversation_id=uuid4(),
        status=status,
        payment_method=PaymentMethod.CASH_ON_DELIVERY,
        customer_name="Customer",
        phone_number="123",
        delivery_address="Address",
        created_at=datetime.now(timezone.utc),
        confirmed_at=datetime.now(timezone.utc),
        items=(
            OrderItem(
                id=uuid4(),
                order_id=order_id,
                product_id=uuid4(),
                product_name="Rice",
                unit="kg",
                unit_price=Decimal(80),
                quantity=Decimal(2),
            ),
        ),
    )


class FakeInventoryRepository(InventoryRepository):
    def __init__(self, order: Order) -> None:
        item = order.items[0]
        self.reservation = InventoryReservation(
            id=uuid4(),
            order_id=order.id,
            product_id=item.product_id,
            quantity=item.quantity,
            status=InventoryReservationStatus.ACTIVE,
            created_at=datetime.now(timezone.utc),
        )
        self.on_hand = Decimal(5)
        self.reserved = item.quantity

    async def reserve_for_order(self, order_id, items):
        return (self.reservation,)

    async def release_for_order(self, order_id):
        if self.reservation.status == InventoryReservationStatus.RELEASED:
            return (self.reservation,)
        if self.reservation.status != InventoryReservationStatus.ACTIVE:
            raise InventoryStateConflictError
        self.reserved -= self.reservation.quantity
        self.reservation = self.reservation.model_copy(
            update={
                "status": InventoryReservationStatus.RELEASED,
                "released_at": datetime.now(timezone.utc),
            }
        )
        return (self.reservation,)

    async def consume_for_order(self, order_id):
        if self.reservation.status == InventoryReservationStatus.CONSUMED:
            return (self.reservation,)
        if self.reservation.status != InventoryReservationStatus.ACTIVE:
            raise InventoryStateConflictError
        self.on_hand -= self.reservation.quantity
        self.reserved -= self.reservation.quantity
        self.reservation = self.reservation.model_copy(
            update={
                "status": InventoryReservationStatus.CONSUMED,
                "consumed_at": datetime.now(timezone.utc),
            }
        )
        return (self.reservation,)

    async def get_balance(self, product_id):
        return InventoryBalance(
            product_id=product_id,
            on_hand_quantity=self.on_hand,
            reserved_quantity=self.reserved,
            updated_at=datetime.now(timezone.utc),
        )


class FakeUnitOfWork(FulfilmentUnitOfWork):
    def __init__(self, order: Order) -> None:
        orders = InMemoryOrderRepository(InMemoryCartRepository())
        orders.orders.append(order)
        self.orders: OrderRepository = orders
        self.inventory: InventoryRepository = FakeInventoryRepository(order)
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1


def service_for(order: Order) -> tuple[FulfilmentService, FakeUnitOfWork]:
    unit_of_work = FakeUnitOfWork(order)
    return FulfilmentService(lambda: unit_of_work), unit_of_work


@pytest.mark.asyncio
async def test_valid_transitions_and_repeated_status_are_idempotent() -> None:
    service, unit_of_work = service_for(make_order())
    actor = FulfilmentActor(actor_id=uuid4(), actor_type=FulfilmentActorType.STAFF)

    preparing = await service.transition_order(
        unit_of_work.orders.orders[0].id,  # type: ignore[attr-defined]
        OrderStatus.PREPARING,
        actor,
    )
    repeated = await service.transition_order(
        preparing.id, OrderStatus.PREPARING, actor
    )

    assert repeated.status == OrderStatus.PREPARING
    assert unit_of_work.commits == 1
    assert len(await unit_of_work.orders.get_status_history(preparing.id)) == 1


@pytest.mark.asyncio
async def test_invalid_jump_is_rejected_without_commit() -> None:
    order = make_order()
    service, unit_of_work = service_for(order)

    with pytest.raises(InvalidOrderTransitionError):
        await service.transition_order(
            order.id,
            OrderStatus.DELIVERED,
            FulfilmentActor(actor_type=FulfilmentActorType.STAFF),
        )

    assert unit_of_work.commits == 0


@pytest.mark.asyncio
async def test_cancellation_releases_inventory_once() -> None:
    order = make_order()
    service, unit_of_work = service_for(order)
    actor = FulfilmentActor(actor_id=uuid4(), actor_type=FulfilmentActorType.STAFF)

    cancelled = await service.transition_order(
        order.id, OrderStatus.CANCELLED, actor, "Customer unavailable"
    )
    repeated = await service.transition_order(order.id, OrderStatus.CANCELLED, actor)
    inventory = unit_of_work.inventory

    assert cancelled == repeated
    assert inventory.reserved == 0  # type: ignore[attr-defined]
    assert inventory.on_hand == 5  # type: ignore[attr-defined]
    assert unit_of_work.commits == 1


@pytest.mark.asyncio
async def test_delivery_consumes_on_hand_and_reserved_once() -> None:
    order = make_order(OrderStatus.OUT_FOR_DELIVERY)
    service, unit_of_work = service_for(order)
    actor = FulfilmentActor(actor_id=uuid4(), actor_type=FulfilmentActorType.STAFF)

    await service.transition_order(order.id, OrderStatus.DELIVERED, actor)
    await service.transition_order(order.id, OrderStatus.DELIVERED, actor)
    inventory = unit_of_work.inventory

    assert inventory.on_hand == 3  # type: ignore[attr-defined]
    assert inventory.reserved == 0  # type: ignore[attr-defined]
    assert unit_of_work.commits == 1


def test_inventory_balance_enforces_reserved_invariant() -> None:
    with pytest.raises(ValueError):
        InventoryBalance(
            product_id=uuid4(),
            on_hand_quantity=Decimal(1),
            reserved_quantity=Decimal(2),
            updated_at=datetime.now(timezone.utc),
        )


@pytest.mark.asyncio
async def test_released_and_consumed_reservations_cannot_cross_terminal_states() -> (
    None
):
    released_inventory = FakeInventoryRepository(make_order())
    await released_inventory.release_for_order(released_inventory.reservation.order_id)
    with pytest.raises(InventoryStateConflictError):
        await released_inventory.consume_for_order(
            released_inventory.reservation.order_id
        )

    consumed_inventory = FakeInventoryRepository(make_order())
    await consumed_inventory.consume_for_order(consumed_inventory.reservation.order_id)
    with pytest.raises(InventoryStateConflictError):
        await consumed_inventory.release_for_order(
            consumed_inventory.reservation.order_id
        )

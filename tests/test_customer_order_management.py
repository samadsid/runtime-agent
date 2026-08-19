from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from commerce.models import (
    CommerceSession,
    FulfilmentActorType,
    OrderStatus,
    OrderSummary,
)
from commerce.services import CustomerOrderService
from runtime.capabilities import CapabilityInput, ExecutionContext
from runtime.capabilities.cancel_order import CancelOrderCapability
from runtime.capabilities.get_order_details import GetOrderDetailsCapability
from runtime.capabilities.list_orders import ListOrdersCapability
from runtime.contracts import ExecutionStatus, GeneratedExecutionOutcome
from tests.test_fulfilment_domain import FakeUnitOfWork, make_order


def input_for(session: CommerceSession, conversation_id, data=None):
    return CapabilityInput[CommerceSession](
        data=data or {},
        session=session,
        context=ExecutionContext(conversation_id=conversation_id),
    )


def setup_orders(status: OrderStatus = OrderStatus.CONFIRMED):
    order = make_order(status)
    unit_of_work = FakeUnitOfWork(order)
    service = CustomerOrderService(unit_of_work.orders, lambda: unit_of_work)
    return order, unit_of_work, service


@pytest.mark.asyncio
async def test_list_orders_is_scoped_stable_and_updates_session() -> None:
    order, unit_of_work, service = setup_orders()
    repository = unit_of_work.orders
    newer = order.model_copy(
        update={
            "id": uuid4(),
            "source_cart_id": uuid4(),
            "created_at": order.created_at + timedelta(seconds=1),
            "confirmed_at": order.confirmed_at + timedelta(seconds=1),
            "items": (),
        }
    )
    other = order.model_copy(
        update={
            "id": uuid4(),
            "source_cart_id": uuid4(),
            "conversation_id": uuid4(),
        }
    )
    repository.orders.extend((newer, other))  # type: ignore[attr-defined]

    output = await ListOrdersCapability(service).execute(
        input_for(CommerceSession(), order.conversation_id)
    )

    assert output.outcome.status == ExecutionStatus.SUCCESS
    assert [summary.order_id for summary in output.session.recent_order_results] == [
        newer.id,
        order.id,
    ]
    assert output.session.recent_order_results[1].item_count == 1
    assert output.session.recent_order_results[1].total_amount == Decimal(160)


@pytest.mark.asyncio
async def test_list_orders_validates_limits() -> None:
    order, _, service = setup_orders()
    capability = ListOrdersCapability(service)

    for limit in (0, 11, True, "5"):
        output = await capability.execute(
            input_for(CommerceSession(), order.conversation_id, {"limit": limit})
        )
        assert output.outcome.status == ExecutionStatus.INVALID_INPUT

    with pytest.raises(ValueError):
        await service.list_orders(order.conversation_id, 11)


@pytest.mark.asyncio
async def test_details_resolves_reference_ordinal_and_latest() -> None:
    order, _, service = setup_orders()
    summary = OrderSummary(
        order_id=order.id,
        public_order_number=order.public_order_number,
        status=order.status,
        created_at=order.created_at,
        item_count=1,
        total_amount=Decimal(160),
    )
    session = CommerceSession(recent_order_results=(summary,))
    capability = GetOrderDetailsCapability(service)

    for data in (
        {"order_reference": str(order.id)},
        {"ordinal": 1},
        {"latest": True},
    ):
        output = await capability.execute(
            input_for(session, order.conversation_id, data)
        )
        assert output.outcome.status == ExecutionStatus.SUCCESS
        assert order.public_order_number in output.outcome.protected_values
        assert str(order.id) not in output.outcome.protected_values
        assert order.phone_number in output.outcome.protected_values


@pytest.mark.asyncio
async def test_details_hides_cross_conversation_order_as_not_found() -> None:
    order, _, service = setup_orders()
    capability = GetOrderDetailsCapability(service)

    unknown = await capability.execute(
        input_for(
            CommerceSession(), order.conversation_id, {"order_reference": str(uuid4())}
        )
    )
    foreign = await capability.execute(
        input_for(
            CommerceSession(), uuid4(), {"order_reference": str(order.id)}
        )
    )

    assert unknown.outcome.status == foreign.outcome.status == ExecutionStatus.NOT_FOUND
    assert unknown.outcome.fragments == foreign.outcome.fragments


@pytest.mark.asyncio
async def test_cancellation_requires_review_then_explicit_confirmation() -> None:
    order, unit_of_work, service = setup_orders()
    capability = CancelOrderCapability(
        service,
        "support@example.com",
        clock=lambda: datetime(2026, 8, 9, tzinfo=timezone.utc),
    )

    review = await capability.execute(
        input_for(
            CommerceSession(),
            order.conversation_id,
            {"order_reference": str(order.id), "confirmed": False},
        )
    )

    assert review.session.pending_order_cancellation is not None
    assert review.session.pending_order_cancellation.order_id == order.id
    assert unit_of_work.orders.orders[0].status == OrderStatus.CONFIRMED  # type: ignore[attr-defined]
    assert unit_of_work.inventory.reserved == Decimal(2)  # type: ignore[attr-defined]
    assert isinstance(review.outcome, GeneratedExecutionOutcome)
    assert review.outcome.follow_up is not None

    confirmed = await capability.execute(
        input_for(
            review.session,
            order.conversation_id,
            {"confirmed": True, "order_reference": str(uuid4())},
        )
    )
    repeated = await service.cancel_confirmed_order(order.conversation_id, order.id)

    assert confirmed.session.pending_order_cancellation is None
    assert repeated.status == OrderStatus.CANCELLED
    assert unit_of_work.inventory.reserved == 0  # type: ignore[attr-defined]
    history = await unit_of_work.orders.get_status_history(order.id)
    assert len(history) == 1
    assert history[0].actor_type == FulfilmentActorType.CUSTOMER


@pytest.mark.asyncio
async def test_cancellation_denies_preparing_and_preserves_inventory() -> None:
    order, unit_of_work, service = setup_orders(OrderStatus.PREPARING)
    capability = CancelOrderCapability(service, "support@example.com")

    output = await capability.execute(
        input_for(
            CommerceSession(),
            order.conversation_id,
            {"latest": True, "confirmed": False},
        )
    )

    assert output.outcome.status == ExecutionStatus.FAILURE
    assert "support@example.com" in output.outcome.protected_values
    assert output.session.pending_order_cancellation is None
    assert unit_of_work.inventory.reserved == Decimal(2)  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_confirmation_without_pending_does_not_cancel() -> None:
    order, unit_of_work, service = setup_orders()

    output = await CancelOrderCapability(service, "support@example.com").execute(
        input_for(CommerceSession(), order.conversation_id, {"confirmed": True})
    )

    assert output.outcome.status == ExecutionStatus.MISSING_INPUT
    assert unit_of_work.orders.orders[0].status == OrderStatus.CONFIRMED  # type: ignore[attr-defined]

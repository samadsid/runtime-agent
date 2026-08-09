from __future__ import annotations

from collections.abc import Callable
from typing import ClassVar
from uuid import UUID

from commerce.models import FulfilmentActor, Order, OrderStatus
from commerce.repositories import (
    FulfilmentUnitOfWork,
    InvalidOrderTransitionError,
    OrderNotFoundError,
)


class FulfilmentService:
    _ALLOWED_TRANSITIONS: ClassVar[dict[OrderStatus, frozenset[OrderStatus]]] = {
        OrderStatus.CONFIRMED: frozenset(
            {OrderStatus.PREPARING, OrderStatus.CANCELLED}
        ),
        OrderStatus.PREPARING: frozenset(
            {OrderStatus.OUT_FOR_DELIVERY, OrderStatus.CANCELLED}
        ),
        OrderStatus.OUT_FOR_DELIVERY: frozenset({OrderStatus.DELIVERED}),
        OrderStatus.DELIVERED: frozenset(),
        OrderStatus.CANCELLED: frozenset(),
    }

    def __init__(
        self, unit_of_work_factory: Callable[[], FulfilmentUnitOfWork]
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    async def transition_order(
        self,
        order_id: UUID,
        target_status: OrderStatus,
        actor: FulfilmentActor,
        reason: str | None = None,
    ) -> Order:
        async with self._unit_of_work_factory() as unit_of_work:
            order = await unit_of_work.orders.get_by_id(order_id, for_update=True)
            if order is None:
                raise OrderNotFoundError(f"Order {order_id} does not exist.")
            if order.status == target_status:
                return order
            if target_status not in self._ALLOWED_TRANSITIONS[order.status]:
                raise InvalidOrderTransitionError(
                    f"Order cannot transition from {order.status.value} "
                    f"to {target_status.value}."
                )

            if target_status == OrderStatus.CANCELLED:
                await unit_of_work.inventory.release_for_order(order_id)
            elif target_status == OrderStatus.DELIVERED:
                await unit_of_work.inventory.consume_for_order(order_id)

            transitioned = await unit_of_work.orders.transition_status(
                order_id, target_status, actor, reason
            )
            await unit_of_work.commit()
            return transitioned

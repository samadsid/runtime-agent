from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from commerce.models import (
    FulfilmentActor,
    FulfilmentActorType,
    Order,
    OrderStatus,
    OrderSummary,
)
from commerce.repositories import (
    CustomerCancellationNotAllowedError,
    FulfilmentUnitOfWork,
    OrderNotFoundError,
    OrderRepository,
)


class CustomerOrderService:
    def __init__(
        self,
        repository: OrderRepository,
        unit_of_work_factory: Callable[[], FulfilmentUnitOfWork],
    ) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    async def list_orders(
        self, conversation_id: UUID, limit: int = 5
    ) -> tuple[OrderSummary, ...]:
        if limit < 1 or limit > 10:
            raise ValueError("Order list limit must be between 1 and 10.")
        return await self._repository.list_for_conversation(conversation_id, limit)

    async def get_order_details(
        self, conversation_id: UUID, order_id: UUID
    ) -> Order:
        order = await self._repository.get_for_conversation(
            conversation_id, order_id
        )
        if order is None:
            raise OrderNotFoundError("Order does not exist for this conversation.")
        return order

    async def get_latest_order(self, conversation_id: UUID) -> Order:
        order = await self._repository.get_latest_for_conversation(conversation_id)
        if order is None:
            raise OrderNotFoundError("No order exists for this conversation.")
        return order

    async def cancel_confirmed_order(
        self, conversation_id: UUID, order_id: UUID
    ) -> Order:
        async with self._unit_of_work_factory() as unit_of_work:
            order = await unit_of_work.orders.get_for_conversation(
                conversation_id, order_id, for_update=True
            )
            if order is None:
                raise OrderNotFoundError(
                    "Order does not exist for this conversation."
                )
            if order.status == OrderStatus.CANCELLED:
                return order
            if order.status != OrderStatus.CONFIRMED:
                raise CustomerCancellationNotAllowedError(order.status)

            await unit_of_work.inventory.release_for_order(order_id)
            cancelled = await unit_of_work.orders.transition_status(
                order_id,
                OrderStatus.CANCELLED,
                FulfilmentActor(actor_type=FulfilmentActorType.CUSTOMER),
            )
            await unit_of_work.commit()
            return cancelled

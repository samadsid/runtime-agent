from __future__ import annotations

from uuid import UUID

from commerce.models import Order
from commerce.repositories import OrderRepository


class OrderService:
    def __init__(self, repository: OrderRepository) -> None:
        self._repository = repository

    async def create_confirmed_order_from_cart(
        self,
        conversation_id: UUID,
        cart_id: UUID,
        customer_name: str,
        phone_number: str,
        delivery_address: str,
    ) -> Order:
        return await self._repository.create_confirmed_order_from_cart(
            conversation_id=conversation_id,
            cart_id=cart_id,
            customer_name=customer_name,
            phone_number=phone_number,
            delivery_address=delivery_address,
        )

    async def get_latest_order(self, conversation_id: UUID) -> Order | None:
        return await self._repository.get_latest_order(conversation_id)

from __future__ import annotations

from uuid import UUID

from commerce.models import ConfirmedOrderResult, Order
from commerce.repositories import OrderConfirmationPersistenceError, OrderRepository


class OrderService:
    def __init__(self, repository: OrderRepository) -> None:
        self._repository = repository

    async def create_confirmed_order_from_cart(
        self,
        tenant_id: UUID,
        conversation_id: UUID,
        cart_id: UUID,
        expected_cart_version: int,
        customer_name: str,
        phone_number: str,
        delivery_address: str,
    ) -> ConfirmedOrderResult:
        try:
            return await self._repository.create_confirmed_order_from_cart(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                cart_id=cart_id,
                expected_cart_version=expected_cart_version,
                customer_name=customer_name,
                phone_number=phone_number,
                delivery_address=delivery_address,
            )
        except OrderConfirmationPersistenceError:
            raise
        except Exception as error:
            raise OrderConfirmationPersistenceError(
                "Could not confirm the order."
            ) from error

    async def get_latest_order(self, conversation_id: UUID) -> Order | None:
        return await self._repository.get_latest_order(conversation_id)

from __future__ import annotations

import logging
from uuid import UUID

from commerce.models import ConfirmedOrderResult, DeliveryLocationSnapshot, Order
from commerce.repositories import OrderConfirmationPersistenceError, OrderRepository

logger = logging.getLogger(__name__)


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
        delivery_location: DeliveryLocationSnapshot | None = None,
    ) -> ConfirmedOrderResult:
        try:
            if delivery_location is None:
                return await self._repository.create_confirmed_order_from_cart(
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                    cart_id=cart_id,
                    expected_cart_version=expected_cart_version,
                    customer_name=customer_name,
                    phone_number=phone_number,
                    delivery_address=delivery_address,
                )
            return await self._repository.create_confirmed_order_from_cart(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                cart_id=cart_id,
                expected_cart_version=expected_cart_version,
                customer_name=customer_name,
                phone_number=phone_number,
                delivery_address=delivery_address,
                delivery_location=delivery_location,
            )
        except OrderConfirmationPersistenceError:
            raise
        except Exception as error:
            logger.exception(
                "Confirmed-order persistence failed.",
                extra={"event": "order_confirmation_persistence_failure"},
            )
            raise OrderConfirmationPersistenceError(
                "Could not confirm the order."
            ) from error

    async def get_latest_order(self, conversation_id: UUID) -> Order | None:
        return await self._repository.get_latest_order(conversation_id)

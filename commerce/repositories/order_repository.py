from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from commerce.models import Order


class OrderRepository(ABC):
    @abstractmethod
    async def create_confirmed_order_from_cart(
        self,
        conversation_id: UUID,
        cart_id: UUID,
        customer_name: str,
        phone_number: str,
        delivery_address: str,
    ) -> Order: ...

    @abstractmethod
    async def get_latest_order(self, conversation_id: UUID) -> Order | None: ...


class CartNotAvailableForCheckoutError(ValueError):
    pass

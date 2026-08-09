from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from uuid import UUID

from commerce.models import Cart


class CartRepository(ABC):
    @abstractmethod
    async def get_or_create_active_cart(
        self, tenant_id: UUID, conversation_id: UUID
    ) -> Cart: ...

    @abstractmethod
    async def add_or_replace_item(
        self, cart_id: UUID, product_id: UUID, quantity: Decimal
    ) -> Cart: ...

    @abstractmethod
    async def get_or_create_active_cart_and_add_or_replace_item(
        self,
        tenant_id: UUID,
        conversation_id: UUID,
        product_id: UUID,
        quantity: Decimal,
    ) -> Cart: ...

    @abstractmethod
    async def get_active_cart(
        self, tenant_id: UUID, conversation_id: UUID
    ) -> Cart | None: ...

    @abstractmethod
    async def remove_item_by_ordinal(self, cart_id: UUID, ordinal: int) -> Cart: ...


class InvalidCartOrdinalError(ValueError):
    pass

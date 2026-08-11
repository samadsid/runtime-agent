from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from uuid import UUID

from commerce.models import AcceptAvailableQuantityResult, Cart


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

    @abstractmethod
    async def update_item_quantity_by_ordinal(
        self,
        tenant_id: UUID,
        conversation_id: UUID,
        ordinal: int,
        quantity: Decimal,
    ) -> Cart: ...

    @abstractmethod
    async def clear_active_cart(
        self,
        tenant_id: UUID,
        conversation_id: UUID,
        cart_id: UUID,
        expected_version: int,
    ) -> Cart: ...

    @abstractmethod
    async def accept_available_quantity(
        self,
        tenant_id: UUID,
        conversation_id: UUID,
        cart_id: UUID,
        expected_version: int,
        product_id: UUID,
        previously_offered: Decimal,
    ) -> AcceptAvailableQuantityResult: ...


class CartNotFoundError(LookupError):
    pass


class CartItemOrdinalError(ValueError):
    pass


class InvalidCartQuantityError(ValueError):
    pass


class StaleCartError(RuntimeError):
    pass


class CartPersistenceError(RuntimeError):
    pass


class InvalidCartOrdinalError(CartItemOrdinalError):
    """Backward-compatible name for existing removal callers."""

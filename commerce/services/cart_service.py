from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from commerce.models import Cart, Product
from commerce.repositories import (
    CartItemOrdinalError,
    CartNotFoundError,
    CartPersistenceError,
    CartRepository,
    InvalidCartQuantityError,
    StaleCartError,
)


class CartService:
    def __init__(self, repository: CartRepository) -> None:
        self._repository = repository

    async def add_or_replace(
        self,
        tenant_id: UUID,
        conversation_id: UUID,
        product: Product,
        quantity: Decimal,
    ) -> Cart:
        return await (
            self._repository.get_or_create_active_cart_and_add_or_replace_item(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                product_id=product.id,
                quantity=quantity,
            )
        )

    async def get_active(
        self, tenant_id: UUID, conversation_id: UUID
    ) -> Cart | None:
        try:
            return await self._repository.get_active_cart(tenant_id, conversation_id)
        except Exception as error:
            raise CartPersistenceError("Could not load the active cart.") from error

    async def remove_by_ordinal(self, cart_id: UUID, ordinal: int) -> Cart:
        return await self._repository.remove_item_by_ordinal(cart_id, ordinal)

    async def update_item_quantity(
        self,
        tenant_id: UUID,
        conversation_id: UUID,
        ordinal: int,
        quantity: Decimal,
    ) -> Cart:
        if not quantity.is_finite() or quantity <= 0:
            raise InvalidCartQuantityError("Cart quantity must be finite and positive.")
        try:
            return await self._repository.update_item_quantity_by_ordinal(
                tenant_id, conversation_id, ordinal, quantity
            )
        except (
            CartNotFoundError,
            CartItemOrdinalError,
            InvalidCartQuantityError,
            StaleCartError,
        ):
            raise
        except Exception as error:
            raise CartPersistenceError("Could not persist the cart update.") from error

    async def clear_cart(
        self,
        tenant_id: UUID,
        conversation_id: UUID,
        cart_id: UUID,
        expected_version: int,
    ) -> Cart:
        try:
            return await self._repository.clear_active_cart(
                tenant_id, conversation_id, cart_id, expected_version
            )
        except (CartNotFoundError, StaleCartError):
            raise
        except Exception as error:
            raise CartPersistenceError("Could not clear the cart.") from error

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from commerce.models import Cart, Product
from commerce.repositories import CartRepository


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
        return await self._repository.get_active_cart(tenant_id, conversation_id)

    async def remove_by_ordinal(self, cart_id: UUID, ordinal: int) -> Cart:
        return await self._repository.remove_item_by_ordinal(cart_id, ordinal)

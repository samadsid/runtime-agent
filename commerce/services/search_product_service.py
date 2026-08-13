from __future__ import annotations

from uuid import UUID

from commerce.models.product import Product
from commerce.repositories.product_repository import ProductRepository


class SearchProductService:
    """
    Application service responsible for product search.

    The service owns business rules around searching products.
    """

    def __init__(
        self,
        product_repository: ProductRepository,
    ) -> None:
        self._product_repository = product_repository

    async def search(
        self,
        tenant_id: UUID,
        query: str,
    ) -> list[Product]:
        """
        Search products matching the user's query.
        """

        query = query.strip()

        if not query:
            return []

        return await self._product_repository.search(tenant_id, query)

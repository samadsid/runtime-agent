from __future__ import annotations

from uuid import UUID

from commerce.models import Product

from .product_repository import ProductRepository


class InMemoryProductRepository(ProductRepository):
    def __init__(
        self,
        products: list[Product],
    ) -> None:

        self._products = tuple(products)

    async def search(
        self,
        tenant_id: UUID,
        query: str,
    ) -> list[Product]:

        normalized_query = query.strip().lower()

        if not normalized_query:
            return []

        del tenant_id
        return [
            product
            for product in self._products
            if normalized_query in product.name.lower() and product.available
        ]

    async def get_by_id(
        self,
        tenant_id: UUID,
        product_id: UUID,
    ) -> Product | None:
        del tenant_id
        for product in self._products:
            if product.id == product_id:
                return product
        return None

    async def search_candidates(self, tenant_id: UUID, query: str) -> list[Product]:
        del tenant_id
        normalized_query = " ".join(query.casefold().split())
        return [
            product
            for product in self._products
            if normalized_query in " ".join(product.name.casefold().split())
        ]

    async def save(
        self,
        product: Product,
    ) -> None:
        self._products += (product,)

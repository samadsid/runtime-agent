from __future__ import annotations

from commerce.models import Product

from .product_repository import ProductRepository
from uuid import UUID

class InMemoryProductRepository(ProductRepository):

    def __init__(
        self,
        products: list[Product],
    ) -> None:

        self._products = tuple(products)

    async def search(
        self,
        query: str,
    ) -> list[Product]:

        normalized_query = query.strip().lower()

        if not normalized_query:
            return []

        return [
            product
            for product in self._products
            if normalized_query in product.name.lower()
        ]
        
    async def get_by_id(
        self,
        product_id: UUID,
    ) -> Product | None:
        for product in self._products:
            if product.id == product_id:
                return product
        return None

    async def save(
        self,
        product: Product,
    ) -> None:
        self._products.append(product)
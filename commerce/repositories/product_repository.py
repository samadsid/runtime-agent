from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from commerce.models import Product


class ProductRepository(ABC):
    @abstractmethod
    async def search(
        self,
        query: str,
    ) -> list[Product]:
        """
        Search products matching the user's query.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_by_id(
        self,
        product_id: UUID,
    ) -> Product | None:
        """
        Retrieve a product by its identifier.
        """
        raise NotImplementedError

    @abstractmethod
    async def save(
        self,
        product: Product,
    ) -> None:
        """
        Persist a product.
        """
        raise NotImplementedError
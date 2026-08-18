from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from commerce.models import (
    CatalogCategoryPage,
    CatalogProductPage,
    CategoryResolution,
    Product,
)


class ProductRepository(ABC):
    @abstractmethod
    async def search(
        self,
        tenant_id: UUID,
        query: str,
    ) -> list[Product]:
        """
        Search products matching the user's query.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_by_id(
        self,
        tenant_id: UUID,
        product_id: UUID,
    ) -> Product | None:
        """
        Retrieve a product by its identifier.
        """
        raise NotImplementedError

    @abstractmethod
    async def search_candidates(self, tenant_id: UUID, query: str) -> list[Product]:
        """Return tenant-scoped candidates, including unavailable products."""
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

    @abstractmethod
    async def count_browsable_products(self, tenant_id: UUID) -> int:
        raise NotImplementedError

    @abstractmethod
    async def list_categories(
        self,
        tenant_id: UUID,
        *,
        page: int,
        page_size: int,
        hide_empty: bool = True,
    ) -> CatalogCategoryPage:
        raise NotImplementedError

    @abstractmethod
    async def resolve_category(
        self, tenant_id: UUID, query: str, *, limit: int, hide_empty: bool = True
    ) -> CategoryResolution:
        raise NotImplementedError

    @abstractmethod
    async def list_browsable_products(
        self,
        tenant_id: UUID,
        *,
        category_id: UUID | None,
        page: int,
        page_size: int,
    ) -> CatalogProductPage:
        raise NotImplementedError

    @abstractmethod
    async def get_browsable_product(
        self, tenant_id: UUID, product_id: UUID
    ) -> Product | None:
        raise NotImplementedError

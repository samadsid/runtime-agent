from __future__ import annotations

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from commerce.models import (
    CatalogCategoryPage,
    CatalogProductPage,
    CategoryResolutionKind,
    Product,
)
from commerce.repositories import ProductRepository


class CatalogBrowsePolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    product_page_size: int = Field(default=10, ge=1, le=100)
    category_page_size: int = Field(default=10, ge=1, le=100)
    direct_product_limit: int = Field(default=10, ge=1, le=1000)
    hide_empty_categories: bool = True


class CatalogBrowseResultKind(str, Enum):
    CATEGORIES = "CATEGORIES"
    PRODUCTS = "PRODUCTS"
    CATEGORY_NOT_FOUND = "CATEGORY_NOT_FOUND"
    EMPTY = "EMPTY"
    CATEGORY_EMPTY = "CATEGORY_EMPTY"
    PRODUCT = "PRODUCT"
    STALE_PRODUCT = "STALE_PRODUCT"


class CatalogBrowseResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: CatalogBrowseResultKind
    categories: CatalogCategoryPage | None = None
    products: CatalogProductPage | None = None
    product: Product | None = None


class CatalogBrowseService:
    def __init__(
        self, repository: ProductRepository, policy: CatalogBrowsePolicy
    ) -> None:
        self._repository = repository
        self.policy = policy

    async def browse(
        self,
        tenant_id: UUID,
        *,
        view: str = "auto",
        category_query: str | None = None,
    ) -> CatalogBrowseResult:
        if category_query is not None:
            resolution = await self._repository.resolve_category(
                tenant_id,
                category_query,
                limit=self.policy.category_page_size,
                hide_empty=self.policy.hide_empty_categories,
            )
            if resolution.kind is CategoryResolutionKind.NONE:
                categories = await self._repository.list_categories(
                    tenant_id,
                    page=1,
                    page_size=self.policy.category_page_size,
                    hide_empty=self.policy.hide_empty_categories,
                )
                return CatalogBrowseResult(
                    kind=CatalogBrowseResultKind.CATEGORY_NOT_FOUND,
                    categories=categories,
                )
            if resolution.kind is CategoryResolutionKind.MULTIPLE:
                return CatalogBrowseResult(
                    kind=CatalogBrowseResultKind.CATEGORIES,
                    categories=CatalogCategoryPage(
                        items=resolution.matches,
                        page=1,
                        has_previous=False,
                        has_next=False,
                    ),
                )
            return await self.products(tenant_id, resolution.matches[0].category_id, 1)

        if view == "categories":
            return await self.categories(tenant_id, 1)
        if view == "products":
            return await self.products(tenant_id, None, 1)
        return await self.categories(tenant_id, 1)

    async def categories(self, tenant_id: UUID, page: int) -> CatalogBrowseResult:
        result = await self._repository.list_categories(
            tenant_id,
            page=page,
            page_size=self.policy.category_page_size,
            hide_empty=self.policy.hide_empty_categories,
        )
        return CatalogBrowseResult(
            kind=CatalogBrowseResultKind.CATEGORIES,
            categories=result,
        )

    async def products(
        self, tenant_id: UUID, category_id: UUID | None, page: int
    ) -> CatalogBrowseResult:
        result = await self._repository.list_browsable_products(
            tenant_id,
            category_id=category_id,
            page=page,
            page_size=self.policy.product_page_size,
        )
        if category_id is not None and not result.items:
            categories = await self._repository.list_categories(
                tenant_id,
                page=1,
                page_size=self.policy.category_page_size,
                hide_empty=self.policy.hide_empty_categories,
            )
            return CatalogBrowseResult(
                kind=CatalogBrowseResultKind.CATEGORY_EMPTY,
                products=result,
                categories=categories,
            )
        return CatalogBrowseResult(
            kind=CatalogBrowseResultKind.PRODUCTS, products=result
        )

    async def select_product(
        self, tenant_id: UUID, product_id: UUID
    ) -> CatalogBrowseResult:
        product = await self._repository.get_browsable_product(tenant_id, product_id)
        return CatalogBrowseResult(
            kind=(
                CatalogBrowseResultKind.PRODUCT
                if product is not None
                else CatalogBrowseResultKind.STALE_PRODUCT
            ),
            product=product,
        )

from __future__ import annotations

from uuid import UUID

from commerce.models import (
    CatalogCategoryOption,
    CatalogCategoryPage,
    CatalogProductOption,
    CatalogProductPage,
    Category,
    CategoryResolution,
    CategoryResolutionKind,
    Product,
)

from .product_repository import ProductRepository


class InMemoryProductRepository(ProductRepository):
    def __init__(
        self,
        products: list[Product],
        categories: list[Category] | None = None,
        product_categories: dict[UUID, UUID] | None = None,
    ) -> None:

        self._products = tuple(products)
        self._categories = tuple(categories or ())
        self._product_categories = product_categories or {}

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

    async def count_browsable_products(self, tenant_id: UUID) -> int:
        del tenant_id
        return len([product for product in self._products if product.available])

    async def list_categories(
        self, tenant_id: UUID, *, page: int, page_size: int
    ) -> CatalogCategoryPage:
        ordered = sorted(
            (
                category
                for category in self._categories
                if category.tenant_id == tenant_id
                and category.is_active
                and any(
                    product.available
                    and self._product_categories.get(product.id) == category.id
                    for product in self._products
                )
            ),
            key=lambda category: (
                category.display_order,
                category.name.casefold(),
                str(category.id),
            ),
        )
        start = (page - 1) * page_size
        selected = ordered[start : start + page_size]
        return CatalogCategoryPage(
            items=tuple(
                CatalogCategoryOption(category_id=item.id, name=item.name)
                for item in selected
            ),
            page=page,
            has_previous=page > 1,
            has_next=start + page_size < len(ordered),
        )

    async def resolve_category(
        self, tenant_id: UUID, query: str, *, limit: int
    ) -> CategoryResolution:
        normalized = " ".join(query.casefold().split())
        matches = sorted(
            (
                category
                for category in self._categories
                if category.tenant_id == tenant_id
                and category.is_active
                and normalized in " ".join(category.name.casefold().split())
            ),
            key=lambda category: (
                category.name.casefold() != normalized,
                category.display_order,
                category.name.casefold(),
                str(category.id),
            ),
        )[:limit]
        options = tuple(
            CatalogCategoryOption(category_id=item.id, name=item.name)
            for item in matches
        )
        if matches and " ".join(matches[0].name.casefold().split()) == normalized:
            options = options[:1]
        kind = (
            CategoryResolutionKind.NONE
            if not options
            else CategoryResolutionKind.ONE
            if len(options) == 1
            else CategoryResolutionKind.MULTIPLE
        )
        return CategoryResolution(kind=kind, matches=options)

    async def list_browsable_products(
        self, tenant_id: UUID, *, category_id: UUID | None, page: int, page_size: int
    ) -> CatalogProductPage:
        del tenant_id
        ordered = sorted(
            (
                product
                for product in self._products
                if product.available
                and (
                    category_id is None
                    or self._product_categories.get(product.id) == category_id
                )
            ),
            key=lambda product: (product.name.casefold(), str(product.id)),
        )
        start = (page - 1) * page_size
        selected = ordered[start : start + page_size]
        return CatalogProductPage(
            items=tuple(
                CatalogProductOption(
                    product_id=item.id,
                    name=item.name,
                    price=item.price,
                    currency=item.currency,
                    unit=item.unit,
                    available=item.available,
                )
                for item in selected
            ),
            category_id=category_id,
            page=page,
            has_previous=page > 1,
            has_next=start + page_size < len(ordered),
        )

    async def get_browsable_product(
        self, tenant_id: UUID, product_id: UUID
    ) -> Product | None:
        product = await self.get_by_id(tenant_id, product_id)
        return product if product is not None and product.available else None

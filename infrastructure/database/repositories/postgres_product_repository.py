from __future__ import annotations

from uuid import UUID

from asyncpg import Record

from commerce.models import (
    CatalogCategoryOption,
    CatalogCategoryPage,
    CatalogProductOption,
    CatalogProductPage,
    CategoryResolution,
    CategoryResolutionKind,
    Product,
)
from commerce.repositories import ProductRepository
from infrastructure.database import DatabasePool


class PostgresProductRepository(ProductRepository):
    def __init__(
        self,
        pool: DatabasePool,
    ) -> None:
        self._pool = pool

    async def search(
        self,
        tenant_id: UUID,
        query: str,
    ) -> list[Product]:

        sql = """
        SELECT
            products.id,
            products.tenant_id,
            products.sku,
            products.name,
            products.price,
            products.currency,
            products.unit,
            products.status,
            balance.on_hand_quantity - balance.reserved_quantity AS sellable_quantity,
            products.created_at,
            products.updated_at
        FROM products
        JOIN inventory_balances AS balance ON balance.product_id = products.id
        WHERE products.status = 'ACTIVE'
          AND products.active = TRUE
          AND products.customer_visible = TRUE
          AND products.tenant_id = $2
          AND balance.on_hand_quantity - balance.reserved_quantity > 0
          AND products.name ILIKE $1
        ORDER BY products.name;
        """

        rows = await self._pool.pool.fetch(
            sql,
            f"%{query}%",
            tenant_id,
        )

        return [self._to_product(row) for row in rows]

    async def get_by_id(
        self,
        tenant_id: UUID,
        product_id: UUID,
    ) -> Product | None:
        row = await self._pool.pool.fetchrow(
            """
            SELECT id, name, price, currency, unit, status
            FROM products
            WHERE tenant_id = $1 AND id = $2
              AND active = TRUE AND customer_visible = TRUE
            """,
            tenant_id,
            product_id,
        )
        return self._to_product(row) if row else None

    async def search_candidates(self, tenant_id: UUID, query: str) -> list[Product]:
        rows = await self._pool.pool.fetch(
            """
            SELECT id, name, price, currency, unit, status
            FROM products
            WHERE tenant_id = $1 AND name ILIKE $2
              AND active = TRUE AND customer_visible = TRUE
            ORDER BY name, id
            """,
            tenant_id,
            f"%{query}%",
        )
        return [self._to_product(row) for row in rows]

    async def save(
        self,
        product: Product,
    ) -> None:
        raise NotImplementedError

    async def count_browsable_products(self, tenant_id: UUID) -> int:
        return await self._pool.pool.fetchval(
            """
            SELECT count(*)
            FROM products AS product
            JOIN inventory_balances AS balance ON balance.product_id = product.id
            WHERE product.tenant_id = $1
              AND product.active = TRUE
              AND product.customer_visible = TRUE
              AND product.status = 'ACTIVE'
              AND balance.on_hand_quantity - balance.reserved_quantity > 0
            """,
            tenant_id,
        )

    async def list_categories(
        self,
        tenant_id: UUID,
        *,
        page: int,
        page_size: int,
        hide_empty: bool = True,
    ) -> CatalogCategoryPage:
        offset = (page - 1) * page_size
        rows = await self._pool.pool.fetch(
            """
            SELECT category.id, category.name
            FROM product_categories AS category
            WHERE category.tenant_id = $1 AND category.active = TRUE
              AND category.customer_visible = TRUE
              AND ($4 = FALSE OR EXISTS (
                SELECT 1 FROM products AS product
                JOIN inventory_balances AS balance ON balance.product_id = product.id
                WHERE product.tenant_id = category.tenant_id
                  AND product.category_id = category.id
                  AND product.active = TRUE
                  AND product.customer_visible = TRUE
                  AND product.status = 'ACTIVE'
                  AND balance.on_hand_quantity - balance.reserved_quantity > 0
              ))
            ORDER BY category.display_order, lower(category.name), category.id
            LIMIT $2 OFFSET $3
            """,
            tenant_id,
            page_size + 1,
            offset,
            hide_empty,
        )
        options = tuple(
            CatalogCategoryOption(category_id=row["id"], name=row["name"])
            for row in rows[:page_size]
        )
        return CatalogCategoryPage(
            items=options,
            page=page,
            has_previous=page > 1,
            has_next=len(rows) > page_size,
        )

    async def resolve_category(
        self, tenant_id: UUID, query: str, *, limit: int, hide_empty: bool = True
    ) -> CategoryResolution:
        normalized = " ".join(query.casefold().split())
        rows = await self._pool.pool.fetch(
            """
            SELECT id, name
            FROM product_categories
            WHERE tenant_id = $1 AND active = TRUE
              AND customer_visible = TRUE
              AND ($5 = FALSE OR EXISTS (
                SELECT 1 FROM products AS product
                JOIN inventory_balances AS balance ON balance.product_id = product.id
                WHERE product.tenant_id = product_categories.tenant_id
                  AND product.category_id = product_categories.id
                  AND product.active = TRUE
                  AND product.customer_visible = TRUE
                  AND product.status = 'ACTIVE'
                  AND balance.on_hand_quantity - balance.reserved_quantity > 0
              ))
              AND lower(regexp_replace(trim(name), '\\s+', ' ', 'g')) LIKE $2
            ORDER BY
              CASE WHEN lower(regexp_replace(trim(name), '\\s+', ' ', 'g')) = $3 THEN 0 ELSE 1 END,
              display_order, lower(name), id
            LIMIT $4
            """,
            tenant_id,
            f"%{normalized}%",
            normalized,
            limit + 1,
            hide_empty,
        )
        matches = tuple(
            CatalogCategoryOption(category_id=row["id"], name=row["name"])
            for row in rows[:limit]
        )
        if rows and " ".join(rows[0]["name"].casefold().split()) == normalized:
            matches = matches[:1]
        kind = (
            CategoryResolutionKind.NONE
            if not matches
            else CategoryResolutionKind.ONE
            if len(matches) == 1
            else CategoryResolutionKind.MULTIPLE
        )
        return CategoryResolution(kind=kind, matches=matches)

    async def list_browsable_products(
        self,
        tenant_id: UUID,
        *,
        category_id: UUID | None,
        page: int,
        page_size: int,
    ) -> CatalogProductPage:
        offset = (page - 1) * page_size
        rows = await self._pool.pool.fetch(
            """
            SELECT product.id, product.name, product.price, product.currency,
                   product.unit, product.status
            FROM products AS product
            JOIN inventory_balances AS balance ON balance.product_id = product.id
            LEFT JOIN product_categories AS category
              ON category.tenant_id = product.tenant_id AND category.id = product.category_id
            WHERE product.tenant_id = $1
              AND ($2::uuid IS NULL OR product.category_id = $2)
              AND ($2::uuid IS NULL OR (category.active = TRUE AND category.customer_visible = TRUE))
              AND product.active = TRUE
              AND product.customer_visible = TRUE
              AND product.status = 'ACTIVE'
              AND balance.on_hand_quantity - balance.reserved_quantity > 0
            ORDER BY coalesce(category.display_order, 0), product.display_order,
                     lower(product.name), product.id
            LIMIT $3 OFFSET $4
            """,
            tenant_id,
            category_id,
            page_size + 1,
            offset,
        )
        options = tuple(
            CatalogProductOption(
                product_id=row["id"],
                name=row["name"],
                price=row["price"],
                currency=row["currency"],
                unit=row["unit"],
                available=row["status"] == "ACTIVE",
            )
            for row in rows[:page_size]
        )
        return CatalogProductPage(
            items=options,
            category_id=category_id,
            page=page,
            has_previous=page > 1,
            has_next=len(rows) > page_size,
        )

    async def get_browsable_product(
        self, tenant_id: UUID, product_id: UUID
    ) -> Product | None:
        row = await self._pool.pool.fetchrow(
            """
            SELECT product.id, product.name, product.price, product.currency,
                   product.unit, product.status
            FROM products AS product
            JOIN inventory_balances AS balance ON balance.product_id = product.id
            LEFT JOIN product_categories AS category
              ON category.tenant_id = product.tenant_id AND category.id = product.category_id
            WHERE product.tenant_id = $1 AND product.id = $2
              AND product.active = TRUE AND product.customer_visible = TRUE
              AND product.status = 'ACTIVE'
              AND (product.category_id IS NULL OR (category.active = TRUE AND category.customer_visible = TRUE))
              AND balance.on_hand_quantity - balance.reserved_quantity > 0
            """,
            tenant_id,
            product_id,
        )
        return self._to_product(row) if row else None

    def _to_product(
        self,
        row: Record,
    ) -> Product:

        return Product(
            id=row["id"],
            name=row["name"],
            price=row["price"],
            currency=row["currency"],
            unit=row["unit"],
            status=row["status"],
        )

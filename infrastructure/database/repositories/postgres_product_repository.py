from __future__ import annotations

from uuid import UUID

from asyncpg import Record

from commerce.models import Product
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
            products.available,
            balance.on_hand_quantity - balance.reserved_quantity AS sellable_quantity,
            products.created_at,
            products.updated_at
        FROM products
        JOIN inventory_balances AS balance ON balance.product_id = products.id
        WHERE products.available = TRUE
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
            SELECT id, name, price, currency, unit, available
            FROM products WHERE tenant_id = $1 AND id = $2
            """,
            tenant_id,
            product_id,
        )
        return self._to_product(row) if row else None

    async def search_candidates(self, tenant_id: UUID, query: str) -> list[Product]:
        rows = await self._pool.pool.fetch(
            """
            SELECT id, name, price, currency, unit, available
            FROM products
            WHERE tenant_id = $1 AND name ILIKE $2
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
            available=row["available"],
        )

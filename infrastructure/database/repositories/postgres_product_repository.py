from __future__ import annotations

from asyncpg import Record

from commerce.models import Product
from commerce.repositories import ProductRepository
from infrastructure.database import DatabasePool
from uuid import UUID

class PostgresProductRepository(ProductRepository):

    def __init__(
        self,
        pool: DatabasePool,
    ) -> None:
        self._pool = pool

    async def search(
        self,
        query: str,
    ) -> list[Product]:

        sql = """
        SELECT
            id,
            tenant_id,
            sku,
            name,
            price,
            currency,
            unit,
            available,
            stock_quantity,
            created_at,
            updated_at
        FROM products
        WHERE available = TRUE
          AND name ILIKE $1
        ORDER BY name;
        """

        rows = await self._pool.pool.fetch(
            sql,
            f"%{query}%",
        )

        return [
            self._to_product(row)
            for row in rows
        ]
        
    async def get_by_id(
        self,
        product_id: UUID,
    ) -> Product | None:
        raise NotImplementedError

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
            tenant_id=row["tenant_id"],
            sku=row["sku"],
            name=row["name"],
            price=row["price"],
            currency=row["currency"],
            unit=row["unit"],
            available=row["available"],
            stock_quantity=row["stock_quantity"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
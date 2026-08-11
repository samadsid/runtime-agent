from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import asyncpg

from commerce.models import (
    AcceptAvailableQuantityResult,
    AvailableQuantityAccepted,
    Cart,
    CartItem,
    CartStatus,
    Product,
    RecoveryAvailabilityChanged,
    StaleCheckout,
    StaleCheckoutReason,
    StockShortage,
)
from commerce.repositories import (
    CartItemOrdinalError,
    CartNotFoundError,
    CartRepository,
    InvalidCartOrdinalError,
    StaleCartError,
)
from infrastructure.database import DatabasePool


class PostgresCartRepository(CartRepository):
    def __init__(self, pool: DatabasePool) -> None:
        self._pool = pool

    async def get_or_create_active_cart(
        self, tenant_id: UUID, conversation_id: UUID
    ) -> Cart:
        async with (
            self._pool.pool.acquire() as connection,
            connection.transaction(),
        ):
            cart_id = await self._get_or_create_id(
                connection, tenant_id, conversation_id
            )
            return await self._load_cart(connection, cart_id)

    async def add_or_replace_item(
        self, cart_id: UUID, product_id: UUID, quantity: Decimal
    ) -> Cart:
        async with (
            self._pool.pool.acquire() as connection,
            connection.transaction(),
        ):
            exists = await connection.fetchval(
                "SELECT id FROM carts WHERE id = $1 AND status = 'ACTIVE' FOR UPDATE",
                cart_id,
            )
            if exists is None:
                raise CartNotFoundError("Active cart no longer exists.")
            await self._upsert_item(connection, cart_id, product_id, quantity)
            await self._increment_version(connection, cart_id)
            return await self._load_cart(connection, cart_id)

    async def get_or_create_active_cart_and_add_or_replace_item(
        self,
        tenant_id: UUID,
        conversation_id: UUID,
        product_id: UUID,
        quantity: Decimal,
    ) -> Cart:
        async with (
            self._pool.pool.acquire() as connection,
            connection.transaction(),
        ):
            cart_id = await self._get_or_create_id(
                connection, tenant_id, conversation_id
            )
            await self._upsert_item(connection, cart_id, product_id, quantity)
            await self._increment_version(connection, cart_id)
            return await self._load_cart(connection, cart_id)

    async def get_active_cart(
        self, tenant_id: UUID, conversation_id: UUID
    ) -> Cart | None:
        async with self._pool.pool.acquire() as connection:
            cart_id = await connection.fetchval(
                """
                SELECT id
                FROM carts
                WHERE tenant_id = $1
                  AND conversation_id = $2
                  AND status = 'ACTIVE'
                """,
                tenant_id,
                conversation_id,
            )
            if cart_id is None:
                return None
            return await self._load_cart(connection, cart_id)

    async def remove_item_by_ordinal(self, cart_id: UUID, ordinal: int) -> Cart:
        async with (
            self._pool.pool.acquire() as connection,
            connection.transaction(),
        ):
            exists = await connection.fetchval(
                """
                SELECT id
                FROM carts
                WHERE id = $1 AND status = 'ACTIVE'
                FOR UPDATE
                """,
                cart_id,
            )
            if exists is None:
                raise InvalidCartOrdinalError("Active cart no longer exists.")

            item_id = await connection.fetchval(
                """
                SELECT id
                FROM cart_items
                WHERE cart_id = $1
                ORDER BY created_at, id
                OFFSET $2 LIMIT 1
                """,
                cart_id,
                ordinal - 1,
            )
            if item_id is None:
                raise InvalidCartOrdinalError(
                    "Cart ordinal does not identify an item."
                )
            await connection.execute("DELETE FROM cart_items WHERE id = $1", item_id)
            await self._increment_version(connection, cart_id)
            return await self._load_cart(connection, cart_id)

    async def update_item_quantity_by_ordinal(
        self,
        tenant_id: UUID,
        conversation_id: UUID,
        ordinal: int,
        quantity: Decimal,
    ) -> Cart:
        async with (
            self._pool.pool.acquire() as connection,
            connection.transaction(),
        ):
            cart_id = await connection.fetchval(
                """
                SELECT id
                FROM carts
                WHERE tenant_id = $1
                  AND conversation_id = $2
                  AND status = 'ACTIVE'
                FOR UPDATE
                """,
                tenant_id,
                conversation_id,
            )
            if cart_id is None:
                raise CartNotFoundError("Active cart no longer exists.")

            item = await connection.fetchrow(
                """
                SELECT id, quantity
                FROM cart_items
                WHERE cart_id = $1
                ORDER BY created_at, id
                OFFSET $2 LIMIT 1
                """,
                cart_id,
                ordinal - 1,
            )
            if item is None:
                raise CartItemOrdinalError(
                    "Cart ordinal does not identify an item."
                )
            if item["quantity"] == quantity:
                return await self._load_cart(connection, cart_id)

            await connection.execute(
                "UPDATE cart_items SET quantity = $1, updated_at = now() WHERE id = $2",
                quantity,
                item["id"],
            )
            await self._increment_version(connection, cart_id)
            return await self._load_cart(connection, cart_id)

    async def clear_active_cart(
        self,
        tenant_id: UUID,
        conversation_id: UUID,
        cart_id: UUID,
        expected_version: int,
    ) -> Cart:
        async with (
            self._pool.pool.acquire() as connection,
            connection.transaction(),
        ):
            current_version = await connection.fetchval(
                """
                SELECT version
                FROM carts
                WHERE id = $1
                  AND tenant_id = $2
                  AND conversation_id = $3
                  AND status = 'ACTIVE'
                FOR UPDATE
                """,
                cart_id,
                tenant_id,
                conversation_id,
            )
            if current_version is None:
                raise CartNotFoundError("Reviewed active cart no longer exists.")
            if current_version != expected_version:
                raise StaleCartError("The cart changed after it was reviewed.")

            await connection.execute(
                "DELETE FROM cart_items WHERE cart_id = $1", cart_id
            )
            await self._increment_version(connection, cart_id)
            return await self._load_cart(connection, cart_id)

    async def accept_available_quantity(
        self,
        tenant_id: UUID,
        conversation_id: UUID,
        cart_id: UUID,
        expected_version: int,
        product_id: UUID,
        previously_offered: Decimal,
    ) -> AcceptAvailableQuantityResult:
        async with (
            self._pool.pool.acquire() as connection,
            connection.transaction(),
        ):
            cart = await connection.fetchrow(
                """
                SELECT id, version
                FROM carts
                WHERE id = $1
                  AND tenant_id = $2
                  AND conversation_id = $3
                  AND status = 'ACTIVE'
                FOR UPDATE
                """,
                cart_id,
                tenant_id,
                conversation_id,
            )
            if cart is None:
                return StaleCheckout(
                    cart_id=cart_id,
                    reason=StaleCheckoutReason.CART_UNAVAILABLE,
                )
            if cart["version"] != expected_version:
                return StaleCheckout(
                    cart_id=cart_id,
                    reason=StaleCheckoutReason.CART_CHANGED,
                )

            item = await connection.fetchrow(
                """
                SELECT ci.id, ci.quantity, p.name, p.unit
                FROM cart_items AS ci
                JOIN products AS p
                  ON p.id = ci.product_id AND p.tenant_id = $3
                WHERE ci.cart_id = $1 AND ci.product_id = $2
                FOR UPDATE OF ci
                """,
                cart_id,
                product_id,
                tenant_id,
            )
            if item is None:
                return StaleCheckout(
                    cart_id=cart_id,
                    reason=StaleCheckoutReason.CART_CHANGED,
                )

            balance = await connection.fetchrow(
                """
                SELECT on_hand_quantity, reserved_quantity
                FROM inventory_balances
                WHERE product_id = $1
                FOR UPDATE
                """,
                product_id,
            )
            available = (
                balance["on_hand_quantity"] - balance["reserved_quantity"]
                if balance is not None
                else Decimal(0)
            )
            if available <= 0:
                return RecoveryAvailabilityChanged(
                    shortage=StockShortage(
                        product_id=product_id,
                        product_name=item["name"],
                        unit=item["unit"],
                        requested_quantity=item["quantity"],
                        available_quantity=Decimal(0),
                    )
                )

            accepted = min(previously_offered, available)
            await connection.execute(
                """
                UPDATE cart_items
                SET quantity = $1, updated_at = now()
                WHERE id = $2
                """,
                accepted,
                item["id"],
            )
            await self._increment_version(connection, cart_id)
            return AvailableQuantityAccepted(
                cart=await self._load_cart(connection, cart_id),
                product_name=item["name"],
                unit=item["unit"],
                quantity=accepted,
            )

    @staticmethod
    async def _get_or_create_id(
        connection: asyncpg.Connection,
        tenant_id: UUID,
        conversation_id: UUID,
    ) -> UUID:
        cart_id = uuid4()
        return await connection.fetchval(
            """
            INSERT INTO carts (
                id, tenant_id, conversation_id, status, created_at, updated_at
            )
            VALUES ($1, $2, $3, 'ACTIVE', now(), now())
            ON CONFLICT (tenant_id, conversation_id)
            WHERE status = 'ACTIVE'
            DO UPDATE SET updated_at = carts.updated_at
            RETURNING id
            """,
            cart_id,
            tenant_id,
            conversation_id,
        )

    @staticmethod
    async def _upsert_item(
        connection: asyncpg.Connection,
        cart_id: UUID,
        product_id: UUID,
        quantity: Decimal,
    ) -> None:
        await connection.execute(
            """
            INSERT INTO cart_items (
                id, cart_id, product_id, quantity, created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, now(), now())
            ON CONFLICT (cart_id, product_id)
            DO UPDATE SET quantity = EXCLUDED.quantity, updated_at = now()
            """,
            uuid4(),
            cart_id,
            product_id,
            quantity,
        )

    @staticmethod
    async def _increment_version(
        connection: asyncpg.Connection, cart_id: UUID
    ) -> None:
        await connection.execute(
            """
            UPDATE carts
            SET version = version + 1, updated_at = now()
            WHERE id = $1
            """,
            cart_id,
        )

    @staticmethod
    async def _load_cart(connection: asyncpg.Connection, cart_id: UUID) -> Cart:
        cart_row = await connection.fetchrow(
            """
            SELECT id, tenant_id, conversation_id, status, version
            FROM carts
            WHERE id = $1
            """,
            cart_id,
        )
        if cart_row is None:
            raise RuntimeError("Cart disappeared during a repository operation.")

        item_rows = await connection.fetch(
            """
            SELECT p.id, p.name, p.price, p.unit, p.available, ci.quantity
            FROM cart_items AS ci
            JOIN products AS p ON p.id = ci.product_id
            WHERE ci.cart_id = $1
            ORDER BY ci.created_at, ci.id
            """,
            cart_id,
        )
        return Cart(
            id=cart_row["id"],
            tenant_id=cart_row["tenant_id"],
            conversation_id=cart_row["conversation_id"],
            status=CartStatus(cart_row["status"]),
            version=cart_row["version"],
            items=tuple(
                CartItem(
                    product=Product(
                        id=row["id"],
                        name=row["name"],
                        price=row["price"],
                        unit=row["unit"],
                        available=row["available"],
                    ),
                    quantity=row["quantity"],
                )
                for row in item_rows
            ),
        )

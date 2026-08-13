from __future__ import annotations

import json
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import asyncpg

from commerce.models import (
    AcceptAvailableQuantityResult,
    AvailableQuantityAccepted,
    Cart,
    CartItem,
    CartStatus,
    DirectCartResult,
    DirectCartResultKind,
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
            changed = await self._upsert_item(connection, cart_id, product_id, quantity)
            if changed:
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
            changed = await self._upsert_item(connection, cart_id, product_id, quantity)
            if changed:
                await self._increment_version(connection, cart_id)
            return await self._load_cart(connection, cart_id)

    async def add_direct_item(
        self,
        tenant_id: UUID,
        conversation_id: UUID,
        product_id: UUID,
        quantity: Decimal,
        canonical_unit: str,
        request_id: str,
        request_fingerprint: str,
    ) -> DirectCartResult:
        async with self._pool.pool.acquire() as connection, connection.transaction():
            claimed = await connection.fetchval(
                """
                INSERT INTO runtime_command_receipts
                    (id,tenant_id,request_id,operation,request_fingerprint,
                     result_payload,created_at)
                VALUES ($1,$2,$3,'direct_cart_add',$4,'{}'::jsonb,now())
                ON CONFLICT (tenant_id,request_id,operation) DO NOTHING
                RETURNING id
                """,
                uuid4(),
                tenant_id,
                request_id,
                request_fingerprint,
            )
            receipt = None
            if claimed is None:
                receipt = await connection.fetchrow(
                    """
                SELECT request_fingerprint, result_payload
                FROM runtime_command_receipts
                WHERE tenant_id=$1 AND request_id=$2 AND operation='direct_cart_add'
                FOR UPDATE
                """,
                    tenant_id,
                    request_id,
                )
            if receipt is not None:
                if receipt["request_fingerprint"] != request_fingerprint:
                    raise ValueError("Request ID was reused with different cart input.")
                payload = receipt["result_payload"]
                if isinstance(payload, str):
                    payload = json.loads(payload)
                return self._direct_result_from_payload(payload)

            product_row = await connection.fetchrow(
                """
                SELECT p.id, p.name, p.price, p.currency, p.unit, p.available,
                       COALESCE(b.on_hand_quantity - b.reserved_quantity, 0) sellable
                FROM products p
                LEFT JOIN inventory_balances b ON b.product_id=p.id
                WHERE p.tenant_id=$1 AND p.id=$2
                FOR UPDATE OF p
                """,
                tenant_id,
                product_id,
            )
            if (
                product_row is None
                or not product_row["available"]
                or product_row["sellable"] <= 0
            ):
                await connection.execute(
                    "DELETE FROM runtime_command_receipts WHERE id=$1", claimed
                )
                return DirectCartResult(kind=DirectCartResultKind.UNAVAILABLE)
            if product_row["unit"] != canonical_unit:
                await connection.execute(
                    "DELETE FROM runtime_command_receipts WHERE id=$1", claimed
                )
                return DirectCartResult(
                    kind=DirectCartResultKind.UNIT_MISMATCH,
                    canonical_unit=product_row["unit"],
                )

            cart_id = await self._get_or_create_id(
                connection, tenant_id, conversation_id
            )
            changed = await self._upsert_item(connection, cart_id, product_id, quantity)
            if changed:
                await self._increment_version(connection, cart_id)
            cart = await self._load_cart(connection, cart_id)
            result = DirectCartResult(
                kind=DirectCartResultKind.ADDED,
                product=self._product(product_row),
                cart=cart,
            )
            await connection.execute(
                """
                UPDATE runtime_command_receipts
                SET result_payload=$4::jsonb
                WHERE tenant_id=$1 AND request_id=$2
                  AND operation='direct_cart_add' AND request_fingerprint=$3
                """,
                tenant_id,
                request_id,
                request_fingerprint,
                json.dumps(self._direct_result_payload(result)),
            )
            return result

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
                raise InvalidCartOrdinalError("Cart ordinal does not identify an item.")
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
                raise CartItemOrdinalError("Cart ordinal does not identify an item.")
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
    ) -> bool:
        existing = await connection.fetchval(
            "SELECT quantity FROM cart_items WHERE cart_id=$1 AND product_id=$2",
            cart_id,
            product_id,
        )
        if existing == quantity:
            return False
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
        return True

    @staticmethod
    def _product(row) -> Product:
        return Product(
            id=row["id"],
            name=row["name"],
            price=row["price"],
            currency=row["currency"],
            unit=row["unit"],
            available=row["available"],
        )

    @staticmethod
    def _direct_result_payload(result: DirectCartResult) -> dict[str, Any]:
        assert result.product is not None and result.cart is not None
        return {
            "product_id": str(result.product.id),
            "cart": {
                "id": str(result.cart.id),
                "tenant_id": str(result.cart.tenant_id),
                "conversation_id": str(result.cart.conversation_id),
                "status": result.cart.status.value,
                "version": result.cart.version,
                "items": [
                    {
                        "product": {
                            "id": str(item.product.id),
                            "name": item.product.name,
                            "price": str(item.product.price),
                            "currency": item.product.currency,
                            "unit": item.product.unit,
                            "available": item.product.available,
                        },
                        "quantity": str(item.quantity),
                    }
                    for item in result.cart.items
                ],
            },
        }

    @staticmethod
    def _direct_result_from_payload(payload: dict[str, Any]) -> DirectCartResult:
        cart_payload = payload["cart"]
        cart = Cart(
            id=UUID(cart_payload["id"]),
            tenant_id=UUID(cart_payload["tenant_id"]),
            conversation_id=UUID(cart_payload["conversation_id"]),
            status=CartStatus(cart_payload["status"]),
            version=cart_payload["version"],
            items=tuple(
                CartItem(
                    product=Product.model_validate(item["product"]),
                    quantity=Decimal(item["quantity"]),
                )
                for item in cart_payload["items"]
            ),
        )
        product_id = UUID(payload["product_id"])
        product = next(
            item.product for item in cart.items if item.product.id == product_id
        )
        return DirectCartResult(
            kind=DirectCartResultKind.ADDED,
            product=product,
            cart=cart,
            idempotent=True,
        )

    @staticmethod
    async def _increment_version(connection: asyncpg.Connection, cart_id: UUID) -> None:
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
            SELECT p.id, p.name, p.price, p.currency, p.unit, p.available,
                   ci.quantity
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
                        currency=row["currency"],
                        unit=row["unit"],
                        available=row["available"],
                    ),
                    quantity=row["quantity"],
                )
                for row in item_rows
            ),
        )

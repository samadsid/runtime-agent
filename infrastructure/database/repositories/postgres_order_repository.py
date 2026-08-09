from __future__ import annotations

from uuid import UUID, uuid4

import asyncpg

from commerce.models import Order, OrderItem, OrderStatus, PaymentMethod
from commerce.repositories import CartNotAvailableForCheckoutError, OrderRepository
from infrastructure.database import DatabasePool


class PostgresOrderRepository(OrderRepository):
    def __init__(self, pool: DatabasePool) -> None:
        self._pool = pool

    async def create_confirmed_order_from_cart(
        self,
        conversation_id: UUID,
        cart_id: UUID,
        customer_name: str,
        phone_number: str,
        delivery_address: str,
    ) -> Order:
        async with (
            self._pool.pool.acquire() as connection,
            connection.transaction(),
        ):
            cart = await connection.fetchrow(
                """
                SELECT id, conversation_id, status
                FROM carts
                WHERE id = $1
                FOR UPDATE
                """,
                cart_id,
            )
            if cart is None or cart["conversation_id"] != conversation_id:
                raise CartNotAvailableForCheckoutError(
                    "The checkout cart does not exist for this conversation."
                )

            existing_order_id = await connection.fetchval(
                "SELECT id FROM orders WHERE source_cart_id = $1", cart_id
            )
            if existing_order_id is not None:
                return await self._load_order(connection, existing_order_id)

            if cart["status"] != "ACTIVE":
                raise CartNotAvailableForCheckoutError(
                    "The checkout cart is no longer active."
                )

            cart_items = await connection.fetch(
                """
                SELECT
                    ci.product_id,
                    ci.quantity,
                    p.name AS product_name,
                    p.unit,
                    p.price AS unit_price
                FROM cart_items AS ci
                JOIN products AS p ON p.id = ci.product_id
                WHERE ci.cart_id = $1
                ORDER BY ci.created_at, ci.id
                """,
                cart_id,
            )
            if not cart_items:
                raise CartNotAvailableForCheckoutError(
                    "An order cannot be created from an empty cart."
                )

            order_id = uuid4()
            await connection.execute(
                """
                INSERT INTO orders (
                    id, source_cart_id, conversation_id, status, payment_method,
                    customer_name, phone_number, delivery_address,
                    created_at, confirmed_at
                )
                VALUES (
                    $1, $2, $3, 'CONFIRMED', 'CASH_ON_DELIVERY',
                    $4, $5, $6, now(), now()
                )
                """,
                order_id,
                cart_id,
                conversation_id,
                customer_name,
                phone_number,
                delivery_address,
            )
            await connection.executemany(
                """
                INSERT INTO order_items (
                    id, order_id, product_id, product_name,
                    unit, unit_price, quantity
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                [
                    (
                        uuid4(),
                        order_id,
                        row["product_id"],
                        row["product_name"],
                        row["unit"],
                        row["unit_price"],
                        row["quantity"],
                    )
                    for row in cart_items
                ],
            )
            await connection.execute(
                """
                UPDATE carts
                SET status = 'CHECKED_OUT', updated_at = now()
                WHERE id = $1
                """,
                cart_id,
            )
            return await self._load_order(connection, order_id)

    async def get_latest_order(self, conversation_id: UUID) -> Order | None:
        async with self._pool.pool.acquire() as connection:
            order_id = await connection.fetchval(
                """
                SELECT id
                FROM orders
                WHERE conversation_id = $1
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                conversation_id,
            )
            if order_id is None:
                return None
            return await self._load_order(connection, order_id)

    @staticmethod
    async def _load_order(
        connection: asyncpg.Connection, order_id: UUID
    ) -> Order:
        row = await connection.fetchrow(
            """
            SELECT
                id, source_cart_id, conversation_id, status, payment_method,
                customer_name, phone_number, delivery_address,
                created_at, confirmed_at
            FROM orders
            WHERE id = $1
            """,
            order_id,
        )
        if row is None:
            raise RuntimeError("Order disappeared during a repository operation.")

        item_rows = await connection.fetch(
            """
            SELECT
                id, order_id, product_id, product_name,
                unit, unit_price, quantity
            FROM order_items
            WHERE order_id = $1
            ORDER BY id
            """,
            order_id,
        )
        return Order(
            id=row["id"],
            source_cart_id=row["source_cart_id"],
            conversation_id=row["conversation_id"],
            status=OrderStatus(row["status"]),
            payment_method=PaymentMethod(row["payment_method"]),
            customer_name=row["customer_name"],
            phone_number=row["phone_number"],
            delivery_address=row["delivery_address"],
            created_at=row["created_at"],
            confirmed_at=row["confirmed_at"],
            items=tuple(OrderItem.model_validate(dict(item)) for item in item_rows),
        )

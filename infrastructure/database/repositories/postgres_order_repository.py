from __future__ import annotations

from uuid import UUID, uuid4

import asyncpg

from commerce.models import (
    FulfilmentActor,
    FulfilmentActorType,
    Order,
    OrderItem,
    OrderStatus,
    OrderStatusHistory,
    OrderSummary,
    PaymentMethod,
)
from commerce.repositories import CartNotAvailableForCheckoutError, OrderRepository
from infrastructure.database import DatabasePool

from .postgres_inventory_repository import PostgresInventoryRepository


class PostgresOrderRepository(OrderRepository):
    def __init__(
        self,
        pool: DatabasePool,
        connection: asyncpg.Connection | None = None,
    ) -> None:
        self._pool = pool
        self._connection = connection

    async def create_confirmed_order_from_cart(
        self,
        conversation_id: UUID,
        cart_id: UUID,
        customer_name: str,
        phone_number: str,
        delivery_address: str,
    ) -> Order:
        if self._connection is None:
            async with (
                self._pool.pool.acquire() as connection,
                connection.transaction(),
            ):
                return await PostgresOrderRepository(
                    self._pool, connection
                ).create_confirmed_order_from_cart(
                    conversation_id,
                    cart_id,
                    customer_name,
                    phone_number,
                    delivery_address,
                )

        connection = self._connection
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

        cart_rows = await connection.fetch(
            """
            SELECT ci.product_id, ci.quantity, p.name AS product_name,
                   p.unit, p.price AS unit_price
            FROM cart_items AS ci
            JOIN products AS p ON p.id = ci.product_id
            WHERE ci.cart_id = $1
            ORDER BY ci.created_at, ci.id
            """,
            cart_id,
        )
        if not cart_rows:
            raise CartNotAvailableForCheckoutError(
                "An order cannot be created from an empty cart."
            )

        order_id = uuid4()
        order_items = tuple(
            OrderItem(
                id=uuid4(),
                order_id=order_id,
                product_id=row["product_id"],
                product_name=row["product_name"],
                unit=row["unit"],
                unit_price=row["unit_price"],
                quantity=row["quantity"],
            )
            for row in cart_rows
        )

        # Lock and validate every balance before creating any order records.
        product_ids = sorted((item.product_id for item in order_items), key=str)
        balance_rows = await connection.fetch(
            """
            SELECT product_id
            FROM inventory_balances
            WHERE product_id = ANY($1::uuid[])
            ORDER BY product_id
            FOR UPDATE
            """,
            product_ids,
        )
        # The inventory repository performs the grounded shortage calculation.
        # It reuses these transaction-held locks when reserving below.
        del balance_rows

        await connection.execute(
            """
            INSERT INTO orders (
                id, source_cart_id, conversation_id, status, payment_method,
                customer_name, phone_number, delivery_address,
                created_at, confirmed_at
            ) VALUES (
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
                id, order_id, product_id, product_name, unit, unit_price, quantity
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            [
                (
                    item.id,
                    item.order_id,
                    item.product_id,
                    item.product_name,
                    item.unit,
                    item.unit_price,
                    item.quantity,
                )
                for item in order_items
            ],
        )
        await PostgresInventoryRepository(self._pool, connection).reserve_for_order(
            order_id, order_items
        )
        await connection.execute(
            """
            UPDATE carts SET status = 'CHECKED_OUT', updated_at = now()
            WHERE id = $1
            """,
            cart_id,
        )
        await connection.execute(
            """
            INSERT INTO order_status_history (
                id, order_id, from_status, to_status, actor_id,
                actor_type, reason, created_at
            ) VALUES ($1, $2, NULL, 'CONFIRMED', NULL, 'CUSTOMER', NULL, now())
            """,
            uuid4(),
            order_id,
        )
        return await self._load_order(connection, order_id)

    async def list_for_conversation(
        self, conversation_id: UUID, limit: int
    ) -> tuple[OrderSummary, ...]:
        if self._connection is None:
            async with self._pool.pool.acquire() as connection:
                return await PostgresOrderRepository(
                    self._pool, connection
                ).list_for_conversation(conversation_id, limit)
        rows = await self._connection.fetch(
            """
            SELECT order_row.id AS order_id, order_row.status,
                   order_row.created_at, COUNT(item.id) AS item_count,
                   COALESCE(SUM(item.unit_price * item.quantity), 0) AS total_amount
            FROM orders AS order_row
            LEFT JOIN order_items AS item ON item.order_id = order_row.id
            WHERE order_row.conversation_id = $1
            GROUP BY order_row.id, order_row.status, order_row.created_at
            ORDER BY order_row.created_at DESC, order_row.id DESC
            LIMIT $2
            """,
            conversation_id,
            limit,
        )
        return tuple(
            OrderSummary(
                order_id=row["order_id"],
                status=OrderStatus(row["status"]),
                created_at=row["created_at"],
                item_count=row["item_count"],
                total_amount=row["total_amount"],
            )
            for row in rows
        )

    async def get_for_conversation(
        self,
        conversation_id: UUID,
        order_id: UUID,
        *,
        for_update: bool = False,
    ) -> Order | None:
        if self._connection is None:
            async with self._pool.pool.acquire() as connection:
                if for_update:
                    async with connection.transaction():
                        return await PostgresOrderRepository(
                            self._pool, connection
                        ).get_for_conversation(
                            conversation_id, order_id, for_update=True
                        )
                return await PostgresOrderRepository(
                    self._pool, connection
                ).get_for_conversation(conversation_id, order_id)
        suffix = " FOR UPDATE" if for_update else ""
        found_id = await self._connection.fetchval(
            f"""
            SELECT id FROM orders
            WHERE conversation_id = $1 AND id = $2{suffix}
            """,
            conversation_id,
            order_id,
        )
        return (
            await self._load_order(self._connection, found_id)
            if found_id is not None
            else None
        )

    async def get_latest_for_conversation(
        self, conversation_id: UUID
    ) -> Order | None:
        if self._connection is None:
            async with self._pool.pool.acquire() as connection:
                return await PostgresOrderRepository(
                    self._pool, connection
                ).get_latest_for_conversation(conversation_id)
        order_id = await self._connection.fetchval(
            """
            SELECT id FROM orders
            WHERE conversation_id = $1
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            conversation_id,
        )
        return (
            await self._load_order(self._connection, order_id)
            if order_id is not None
            else None
        )

    async def get_latest_order(self, conversation_id: UUID) -> Order | None:
        return await self.get_latest_for_conversation(conversation_id)

    async def get_by_id(
        self, order_id: UUID, *, for_update: bool = False
    ) -> Order | None:
        if self._connection is None:
            async with self._pool.pool.acquire() as connection:
                if for_update:
                    async with connection.transaction():
                        return await PostgresOrderRepository(
                            self._pool, connection
                        ).get_by_id(order_id, for_update=True)
                return await PostgresOrderRepository(self._pool, connection).get_by_id(
                    order_id
                )
        suffix = " FOR UPDATE" if for_update else ""
        exists = await self._connection.fetchval(
            f"SELECT id FROM orders WHERE id = $1{suffix}", order_id
        )
        return (
            await self._load_order(self._connection, order_id)
            if exists is not None
            else None
        )

    async def transition_status(
        self,
        order_id: UUID,
        target_status: OrderStatus,
        actor: FulfilmentActor,
        reason: str | None = None,
    ) -> Order:
        if self._connection is None:
            async with (
                self._pool.pool.acquire() as connection,
                connection.transaction(),
            ):
                return await PostgresOrderRepository(
                    self._pool, connection
                ).transition_status(order_id, target_status, actor, reason)
        current = await self.get_by_id(order_id, for_update=True)
        if current is None:
            raise RuntimeError("Order disappeared during a status transition.")
        if current.status == target_status:
            return current
        await self._connection.execute(
            "UPDATE orders SET status = $2 WHERE id = $1",
            order_id,
            target_status.value,
        )
        await self._connection.execute(
            """
            INSERT INTO order_status_history (
                id, order_id, from_status, to_status, actor_id,
                actor_type, reason, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, now())
            """,
            uuid4(),
            order_id,
            current.status.value,
            target_status.value,
            actor.actor_id,
            actor.actor_type.value,
            reason,
        )
        transitioned = await self._load_order(self._connection, order_id)
        return transitioned

    async def get_status_history(
        self, order_id: UUID
    ) -> tuple[OrderStatusHistory, ...]:
        if self._connection is None:
            async with self._pool.pool.acquire() as connection:
                return await PostgresOrderRepository(
                    self._pool, connection
                ).get_status_history(order_id)
        rows = await self._connection.fetch(
            """
            SELECT id, order_id, from_status, to_status, actor_id,
                   actor_type, reason, created_at
            FROM order_status_history
            WHERE order_id = $1
            ORDER BY created_at, id
            """,
            order_id,
        )
        return tuple(
            OrderStatusHistory(
                id=row["id"],
                order_id=row["order_id"],
                from_status=(
                    OrderStatus(row["from_status"])
                    if row["from_status"] is not None
                    else None
                ),
                to_status=OrderStatus(row["to_status"]),
                actor_id=row["actor_id"],
                actor_type=FulfilmentActorType(row["actor_type"]),
                reason=row["reason"],
                created_at=row["created_at"],
            )
            for row in rows
        )

    @staticmethod
    async def _load_order(connection: asyncpg.Connection, order_id: UUID) -> Order:
        row = await connection.fetchrow(
            """
            SELECT id, source_cart_id, conversation_id, status, payment_method,
                   customer_name, phone_number, delivery_address,
                   created_at, confirmed_at
            FROM orders WHERE id = $1
            """,
            order_id,
        )
        if row is None:
            raise RuntimeError("Order disappeared during a repository operation.")
        item_rows = await connection.fetch(
            """
            SELECT id, order_id, product_id, product_name,
                   unit, unit_price, quantity
            FROM order_items WHERE order_id = $1
            ORDER BY id
            """,
            order_id,
        )
        history_rows = await connection.fetch(
            """
            SELECT id, order_id, from_status, to_status, actor_id,
                   actor_type, reason, created_at
            FROM order_status_history
            WHERE order_id = $1
            ORDER BY created_at, id
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
            status_history=tuple(
                OrderStatusHistory(
                    id=history["id"],
                    order_id=history["order_id"],
                    from_status=(
                        OrderStatus(history["from_status"])
                        if history["from_status"] is not None
                        else None
                    ),
                    to_status=OrderStatus(history["to_status"]),
                    actor_id=history["actor_id"],
                    actor_type=FulfilmentActorType(history["actor_type"]),
                    reason=history["reason"],
                    created_at=history["created_at"],
                )
                for history in history_rows
            ),
        )

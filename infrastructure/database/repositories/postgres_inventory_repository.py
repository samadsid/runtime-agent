from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import asyncpg

from commerce.models import (
    InventoryBalance,
    InventoryReservation,
    InventoryReservationStatus,
    OrderItem,
    StockShortage,
)
from commerce.repositories import (
    InsufficientStockError,
    InventoryRepository,
    InventoryStateConflictError,
)
from infrastructure.database import DatabasePool


class PostgresInventoryRepository(InventoryRepository):
    def __init__(
        self,
        pool: DatabasePool,
        connection: asyncpg.Connection | None = None,
    ) -> None:
        self._pool = pool
        self._connection = connection

    async def reserve_for_order(
        self, order_id: UUID, items: tuple[OrderItem, ...]
    ) -> tuple[InventoryReservation, ...]:
        if self._connection is None:
            async with (
                self._pool.pool.acquire() as connection,
                connection.transaction(),
            ):
                return await PostgresInventoryRepository(
                    self._pool, connection
                ).reserve_for_order(order_id, items)

        existing = await self._load_for_order(order_id)
        if existing:
            return existing

        product_ids = sorted({item.product_id for item in items}, key=str)
        rows = await self._connection.fetch(
            """
            SELECT product_id, tenant_id, on_hand_quantity, reserved_quantity
            FROM inventory_balances
            WHERE product_id = ANY($1::uuid[])
            ORDER BY product_id
            FOR UPDATE
            """,
            product_ids,
        )
        balances = {row["product_id"]: row for row in rows}
        shortages = tuple(
            StockShortage(
                product_id=item.product_id,
                product_name=item.product_name,
                requested_quantity=item.quantity,
                available_quantity=(
                    balances[item.product_id]["on_hand_quantity"]
                    - balances[item.product_id]["reserved_quantity"]
                    if item.product_id in balances
                    else Decimal(0)
                ),
                unit=item.unit,
            )
            for item in items
            if item.product_id not in balances
            or item.quantity
            > balances[item.product_id]["on_hand_quantity"]
            - balances[item.product_id]["reserved_quantity"]
        )
        if shortages:
            raise InsufficientStockError(shortages)

        tenant_id = await self._connection.fetchval(
            """SELECT c.tenant_id FROM orders o JOIN carts c ON c.id=o.source_cart_id
               WHERE o.id=$1""", order_id,
        )
        reservations = [(uuid4(), order_id, item.product_id, item.quantity) for item in items]
        await self._connection.executemany(
            """
            UPDATE inventory_balances
            SET reserved_quantity = reserved_quantity + $2, version=version+1, updated_at = now()
            WHERE product_id = $1
            """,
            [(item.product_id, item.quantity) for item in items],
        )
        await self._connection.executemany(
            """
            INSERT INTO inventory_reservations (
                id, order_id, product_id, quantity, status, created_at
            ) VALUES ($1, $2, $3, $4, 'ACTIVE', now())
            """,
            reservations,
        )
        await self._connection.executemany(
            """INSERT INTO inventory_movements
               (id,tenant_id,product_id,movement_type,quantity,on_hand_delta,reserved_delta,
                on_hand_before,on_hand_after,reserved_before,reserved_after,reference_type,
                reference_id,reason,actor_type,created_at)
               VALUES ($1,$2,$3,'RESERVATION',$4,0,$4,$5,$5,$6,$6+$4,
                       'INVENTORY_RESERVATION',$7,'Order reservation','SYSTEM',now())""",
            [
                (uuid4(), tenant_id, item.product_id, item.quantity,
                 balances[item.product_id]["on_hand_quantity"],
                 balances[item.product_id]["reserved_quantity"], reservation[0])
                for item, reservation in zip(items, reservations, strict=True)
            ],
        )
        return await self._load_for_order(order_id)

    async def release_for_order(
        self, order_id: UUID
    ) -> tuple[InventoryReservation, ...]:
        return await self._finish_for_order(order_id, release=True)

    async def consume_for_order(
        self, order_id: UUID
    ) -> tuple[InventoryReservation, ...]:
        return await self._finish_for_order(order_id, release=False)

    async def get_balance(self, product_id: UUID) -> InventoryBalance | None:
        if self._connection is None:
            async with self._pool.pool.acquire() as connection:
                return await PostgresInventoryRepository(
                    self._pool, connection
                ).get_balance(product_id)
        row = await self._connection.fetchrow(
            """
            SELECT product_id, tenant_id, on_hand_quantity, reserved_quantity, version, updated_at
            FROM inventory_balances
            WHERE product_id = $1
            """,
            product_id,
        )
        return InventoryBalance.model_validate(dict(row)) if row else None

    async def _finish_for_order(
        self, order_id: UUID, *, release: bool
    ) -> tuple[InventoryReservation, ...]:
        if self._connection is None:
            async with (
                self._pool.pool.acquire() as connection,
                connection.transaction(),
            ):
                return await PostgresInventoryRepository(
                    self._pool, connection
                )._finish_for_order(order_id, release=release)

        reservations = await self._connection.fetch(
            """
            SELECT id, order_id, product_id, quantity, status,
                   created_at, released_at, consumed_at
            FROM inventory_reservations
            WHERE order_id = $1
            ORDER BY product_id
            FOR UPDATE
            """,
            order_id,
        )
        if not reservations:
            raise InventoryStateConflictError(
                "The order has no inventory reservations."
            )

        expected_terminal = "RELEASED" if release else "CONSUMED"
        statuses = {row["status"] for row in reservations}
        if statuses == {expected_terminal}:
            return tuple(self._to_reservation(row) for row in reservations)
        if statuses != {"ACTIVE"}:
            raise InventoryStateConflictError(
                "Reservations are not in a consistent active state."
            )

        product_ids = [row["product_id"] for row in reservations]
        balance_rows = await self._connection.fetch(
            """
            SELECT product_id, tenant_id, on_hand_quantity, reserved_quantity
            FROM inventory_balances
            WHERE product_id = ANY($1::uuid[])
            ORDER BY product_id
            FOR UPDATE
            """,
            sorted(product_ids, key=str),
        )
        balances = {row["product_id"]: row for row in balance_rows}
        if len(balances) != len(product_ids) or any(
            row["reserved_quantity"] < reservation["quantity"]
            or (not release and row["on_hand_quantity"] < reservation["quantity"])
            for reservation in reservations
            if (row := balances.get(reservation["product_id"])) is not None
        ):
            raise InventoryStateConflictError(
                "Inventory balances do not match the active reservations."
            )

        await self._connection.executemany(
            """
            UPDATE inventory_balances
            SET on_hand_quantity = on_hand_quantity - $2,
                reserved_quantity = reserved_quantity - $3,
                version=version+1, updated_at = now()
            WHERE product_id = $1
            """,
            [
                (
                    row["product_id"],
                    0 if release else row["quantity"],
                    row["quantity"],
                )
                for row in reservations
            ],
        )
        movement_type = "RELEASE" if release else "CONSUMPTION"
        reason = "Order reservation release" if release else "Order inventory consumption"
        await self._connection.executemany(
            """INSERT INTO inventory_movements
               (id,tenant_id,product_id,movement_type,quantity,on_hand_delta,reserved_delta,
                on_hand_before,on_hand_after,reserved_before,reserved_after,reference_type,
                reference_id,reason,actor_type,created_at)
               VALUES ($1,$2,$3,$4,$5,$6,-$5,$7,$8,$9,$9-$5,
                       'INVENTORY_RESERVATION',$10,$11,'SYSTEM',now())""",
            [
                (
                    uuid4(), balances[row["product_id"]]["tenant_id"], row["product_id"],
                    movement_type, row["quantity"], 0 if release else -row["quantity"],
                    balances[row["product_id"]]["on_hand_quantity"],
                    balances[row["product_id"]]["on_hand_quantity"] - (0 if release else row["quantity"]),
                    balances[row["product_id"]]["reserved_quantity"], row["id"], reason,
                )
                for row in reservations
            ],
        )
        timestamp_column = "released_at" if release else "consumed_at"
        await self._connection.execute(
            f"""
            UPDATE inventory_reservations
            SET status = $2, {timestamp_column} = now()
            WHERE order_id = $1 AND status = 'ACTIVE'
            """,
            order_id,
            expected_terminal,
        )
        return await self._load_for_order(order_id)

    async def _load_for_order(self, order_id: UUID) -> tuple[InventoryReservation, ...]:
        assert self._connection is not None
        rows = await self._connection.fetch(
            """
            SELECT id, order_id, product_id, quantity, status,
                   created_at, released_at, consumed_at
            FROM inventory_reservations
            WHERE order_id = $1
            ORDER BY product_id
            """,
            order_id,
        )
        return tuple(self._to_reservation(row) for row in rows)

    @staticmethod
    def _to_reservation(row: asyncpg.Record) -> InventoryReservation:
        return InventoryReservation(
            id=row["id"],
            order_id=row["order_id"],
            product_id=row["product_id"],
            quantity=row["quantity"],
            status=InventoryReservationStatus(row["status"]),
            created_at=row["created_at"],
            released_at=row["released_at"],
            consumed_at=row["consumed_at"],
        )

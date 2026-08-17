from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import asyncpg

from commerce.models import (
    AdminProduct,
    AdminProductPage,
    CatalogOption,
    InventoryMovement,
    InventoryMovementPage,
    InventoryMovementType,
    InventorySummary,
    ProductStatus,
    ProductWithInventory,
    StockState,
)
from infrastructure.database import DatabasePool


class CatalogAdminConflict(ValueError):
    def __init__(self, code: str, current: ProductWithInventory | None = None) -> None:
        self.code = code
        self.current = current


class CatalogAdminNotFound(LookupError):
    pass


class CatalogAdminAccessDenied(PermissionError):
    pass


class CatalogAdminInvalidCursor(ValueError):
    pass


def encode_cursor(values: list[Any]) -> str:
    raw = json.dumps(values, separators=(",", ":"), default=str).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(value: str | None, size: int) -> list[Any] | None:
    if not value:
        return None
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        result = json.loads(raw)
        if not isinstance(result, list) or len(result) != size:
            raise ValueError
        return result
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        raise CatalogAdminInvalidCursor from error


class PostgresCatalogAdminRepository:
    def __init__(self, pool: DatabasePool, retention_hours: int) -> None:
        self._pool = pool
        self._retention_hours = retention_hours

    async def list_options(self, tenant_id: UUID) -> tuple[CatalogOption, ...]:
        rows = await self._pool.pool.fetch(
            """SELECT id,name FROM product_categories
               WHERE tenant_id=$1 AND active=true
               ORDER BY display_order,lower(name),id""",
            tenant_id,
        )
        return tuple(CatalogOption(id=row["id"], name=row["name"]) for row in rows)

    async def list_products(
        self, tenant_id: UUID, *, status: ProductStatus | None,
        category_id: UUID | None, query: str | None, stock_state: StockState | None,
        limit: int, cursor: str | None,
    ) -> AdminProductPage:
        after = decode_cursor(cursor, 3)
        rows = await self._pool.pool.fetch(
            """
            SELECT p.*,c.name AS category_name,b.on_hand_quantity,b.reserved_quantity,
                   b.version AS inventory_version,b.updated_at AS inventory_updated_at
            FROM products p
            JOIN inventory_balances b ON b.tenant_id=p.tenant_id AND b.product_id=p.id
            LEFT JOIN product_categories c ON c.tenant_id=p.tenant_id AND c.id=p.category_id
            WHERE p.tenant_id=$1
              AND ($2::text IS NULL OR p.status=$2)
              AND ($3::uuid IS NULL OR p.category_id=$3)
              AND ($4::text IS NULL OR p.name ILIKE '%' || $4 || '%'
                   OR p.sku_normalized LIKE '%' || $4 || '%')
              AND ($5::text IS NULL
                OR ($5='OUT' AND p.status='ACTIVE' AND b.on_hand_quantity-b.reserved_quantity=0)
                OR ($5='AVAILABLE' AND p.status='ACTIVE' AND b.on_hand_quantity-b.reserved_quantity>0)
                OR ($5='LOW' AND p.status='ACTIVE' AND p.low_stock_threshold IS NOT NULL
                    AND b.on_hand_quantity-b.reserved_quantity<=p.low_stock_threshold))
              AND ($6::integer IS NULL OR (p.display_order,lower(p.name),p.id) >
                  ($6, $7::text, $8::uuid))
            ORDER BY p.display_order,lower(p.name),p.id LIMIT $9
            """,
            tenant_id, status.value if status else None, category_id, query,
            stock_state.value if stock_state else None,
            int(after[0]) if after else None, str(after[1]) if after else None,
            UUID(after[2]) if after else None, limit + 1,
        )
        items = tuple(self._to_product(row) for row in rows[:limit])
        next_cursor = None
        if len(rows) > limit:
            row = rows[limit - 1]
            next_cursor = encode_cursor([row["display_order"], row["name"].lower(), row["id"]])
        return AdminProductPage(items=items, next_cursor=next_cursor)

    async def get_product(self, tenant_id: UUID, product_id: UUID) -> ProductWithInventory | None:
        row = await self._pool.pool.fetchrow(self._product_sql() + " WHERE p.tenant_id=$1 AND p.id=$2", tenant_id, product_id)
        return self._to_product(row) if row else None

    async def create_product(
        self, *, tenant_id: UUID, staff_id: UUID, key: str, request_hash: str,
        values: dict[str, Any],
    ) -> ProductWithInventory:
        product_id = uuid4()
        async with self._pool.pool.acquire() as connection, connection.transaction():
            replay = await self._claim_idempotency(connection, tenant_id, staff_id, key, "CREATE_PRODUCT", request_hash, product_id)
            if replay is not None:
                return await self._replay_product(connection, tenant_id, replay)
            await self._authorize(connection, tenant_id, staff_id)
            await self._validate_category(connection, tenant_id, values.get("category_id"))
            try:
                await connection.execute(
                    """INSERT INTO products
                       (id,tenant_id,sku,sku_normalized,name,price,currency,unit,status,
                        category_id,low_stock_threshold,display_order,version,active,
                        customer_visible,stock_quantity,created_at,updated_at)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,1,true,true,0,now(),now())""",
                    product_id, tenant_id, values["sku"], values["sku_normalized"],
                    values["name"], values["price"], values["currency"], values["unit"],
                    values["status"].value, values.get("category_id"),
                    values.get("low_stock_threshold"), values["display_order"],
                )
            except asyncpg.UniqueViolationError as error:
                raise CatalogAdminConflict("sku_already_exists") from error
            await connection.execute(
                """INSERT INTO inventory_balances
                   (product_id,tenant_id,on_hand_quantity,reserved_quantity,version,updated_at)
                   VALUES ($1,$2,0,0,1,now())""", product_id, tenant_id,
            )
            await connection.execute(
                """INSERT INTO catalog_change_history
                   (id,tenant_id,product_id,change_type,from_version,to_version,changes,actor_id,created_at)
                   VALUES ($1,$2,$3,'CREATED',NULL,1,$4::jsonb,$5,now())""",
                uuid4(), tenant_id, product_id,
                json.dumps({key: {"before": None, "after": self._json(value)} for key, value in values.items() if key != "sku_normalized"}), staff_id,
            )
            result = await self._get_locked_product(connection, tenant_id, product_id)
            await self._finish_idempotency(connection, tenant_id, staff_id, key, {"resource_id": str(product_id)})
            return result

    async def update_product(
        self, *, tenant_id: UUID, staff_id: UUID, product_id: UUID, expected_version: int,
        key: str, request_hash: str, changes: dict[str, Any], change_type: str = "UPDATED",
    ) -> ProductWithInventory:
        async with self._pool.pool.acquire() as connection, connection.transaction():
            replay = await self._claim_idempotency(connection, tenant_id, staff_id, key, "CHANGE_PRODUCT_STATUS" if "status" in changes else "UPDATE_PRODUCT", request_hash, product_id)
            if replay is not None:
                return await self._replay_product(connection, tenant_id, replay)
            await self._authorize(connection, tenant_id, staff_id)
            current = await self._get_locked_product(connection, tenant_id, product_id)
            if current.product.version != expected_version:
                raise CatalogAdminConflict("stale_product_version", current)
            await self._validate_category(connection, tenant_id, changes.get("category_id"))
            if "unit" in changes and changes["unit"] != current.product.unit:
                used = await connection.fetchval(
                    """SELECT EXISTS(
                         SELECT 1 FROM inventory_movements WHERE tenant_id=$1 AND product_id=$2
                         UNION ALL SELECT 1 FROM inventory_balances WHERE tenant_id=$1 AND product_id=$2 AND (on_hand_quantity<>0 OR reserved_quantity<>0)
                         UNION ALL SELECT 1 FROM inventory_reservations WHERE product_id=$2
                         UNION ALL SELECT 1 FROM cart_items WHERE product_id=$2
                         UNION ALL SELECT 1 FROM order_items WHERE product_id=$2)""",
                    tenant_id, product_id,
                )
                if used:
                    raise CatalogAdminConflict("product_unit_locked", current)
            before = current.product.model_dump()
            effective = {name: value for name, value in changes.items() if before.get(name) != value and name not in {"reason", "sku_normalized"}}
            if not effective:
                await self._finish_idempotency(connection, tenant_id, staff_id, key, {"resource_id": str(product_id)})
                return current
            assignments: list[str] = []
            arguments: list[Any] = [tenant_id, product_id]
            for name, value in effective.items():
                assignments.append(f"{name}=${len(arguments)+1}")
                arguments.append(value.value if isinstance(value, ProductStatus) else value)
                if name == "sku":
                    assignments.append(f"sku_normalized=${len(arguments)+1}")
                    arguments.append(changes["sku_normalized"])
            try:
                await connection.execute(
                    f"UPDATE products SET {','.join(assignments)},version=version+1,updated_at=now() WHERE tenant_id=$1 AND id=$2",
                    *arguments,
                )
            except asyncpg.UniqueViolationError as error:
                raise CatalogAdminConflict("sku_already_exists", current) from error
            result = await self._get_locked_product(connection, tenant_id, product_id)
            history_changes = {name: {"before": self._json(before.get(name)), "after": self._json(value)} for name, value in effective.items() if name != "sku_normalized"}
            if changes.get("reason"):
                history_changes["reason"] = changes["reason"]
            await connection.execute(
                """INSERT INTO catalog_change_history
                   (id,tenant_id,product_id,change_type,from_version,to_version,changes,actor_id,created_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8,now())""",
                uuid4(), tenant_id, product_id, change_type, expected_version,
                result.product.version, json.dumps(history_changes), staff_id,
            )
            await self._finish_idempotency(connection, tenant_id, staff_id, key, {"resource_id": str(product_id)})
            return result

    async def adjust_inventory(
        self, *, tenant_id: UUID, staff_id: UUID, product_id: UUID,
        expected_version: int, key: str, request_hash: str,
        movement_type: InventoryMovementType, quantity: Decimal, reason: str,
    ) -> tuple[ProductWithInventory, InventoryMovement, bool]:
        async with self._pool.pool.acquire() as connection, connection.transaction():
            replay = await self._claim_idempotency(connection, tenant_id, staff_id, key, "ADJUST_INVENTORY", request_hash, product_id)
            if replay is not None:
                product = await self._replay_product(connection, tenant_id, replay)
                movement = await connection.fetchrow("SELECT * FROM inventory_movements WHERE tenant_id=$1 AND actor_id=$2 AND idempotency_key=$3", tenant_id, staff_id, key)
                return product, self._to_movement(movement), True
            await self._authorize(connection, tenant_id, staff_id)
            product = await self._get_locked_product(connection, tenant_id, product_id)
            balance = await connection.fetchrow("SELECT * FROM inventory_balances WHERE tenant_id=$1 AND product_id=$2 FOR UPDATE", tenant_id, product_id)
            if balance["version"] != expected_version:
                raise CatalogAdminConflict("stale_inventory_version", product)
            last = await connection.fetchrow("SELECT on_hand_after,reserved_after FROM inventory_movements WHERE tenant_id=$1 AND product_id=$2 ORDER BY created_at DESC,id DESC LIMIT 1", tenant_id, product_id)
            if last and (last["on_hand_after"] != balance["on_hand_quantity"] or last["reserved_after"] != balance["reserved_quantity"]):
                raise CatalogAdminConflict("inventory_reconciliation_failed", product)
            totals = await connection.fetchrow(
                """SELECT coalesce(sum(on_hand_delta),0) AS on_hand,
                          coalesce(sum(reserved_delta),0) AS reserved
                   FROM inventory_movements WHERE tenant_id=$1 AND product_id=$2""",
                tenant_id, product_id,
            )
            active_reserved = await connection.fetchval(
                """SELECT coalesce(sum(quantity),0) FROM inventory_reservations
                   WHERE product_id=$1 AND status='ACTIVE'""", product_id,
            )
            if (
                totals["on_hand"] != balance["on_hand_quantity"]
                or totals["reserved"] != balance["reserved_quantity"]
                or active_reserved != balance["reserved_quantity"]
            ):
                raise CatalogAdminConflict("inventory_reconciliation_failed", product)
            direction = Decimal(1) if movement_type in {InventoryMovementType.RECEIPT, InventoryMovementType.POSITIVE_CORRECTION} else Decimal(-1)
            on_after = balance["on_hand_quantity"] + direction * quantity
            if on_after < balance["reserved_quantity"]:
                raise CatalogAdminConflict("insufficient_unreserved_stock", product)
            movement_id = uuid4()
            await connection.execute("UPDATE inventory_balances SET on_hand_quantity=$3,version=version+1,updated_at=now() WHERE tenant_id=$1 AND product_id=$2", tenant_id, product_id, on_after)
            row = await connection.fetchrow(
                """INSERT INTO inventory_movements
                   (id,tenant_id,product_id,movement_type,quantity,on_hand_delta,reserved_delta,
                    on_hand_before,on_hand_after,reserved_before,reserved_after,reason,actor_type,
                    actor_id,idempotency_key,created_at)
                   VALUES ($1,$2,$3,$4,$5,$6,0,$7,$8,$9,$9,$10,'STAFF',$11,$12,now()) RETURNING *""",
                movement_id, tenant_id, product_id, movement_type.value, quantity,
                direction * quantity, balance["on_hand_quantity"], on_after,
                balance["reserved_quantity"], reason, staff_id, key,
            )
            result = await self._get_locked_product(connection, tenant_id, product_id)
            await self._finish_idempotency(connection, tenant_id, staff_id, key, {"resource_id": str(product_id), "movement_id": str(movement_id)})
            return result, self._to_movement(row), False

    async def list_movements(self, tenant_id: UUID, product_id: UUID, *, movement_type: InventoryMovementType | None, created_from: datetime | None, created_to: datetime | None, limit: int, cursor: str | None) -> InventoryMovementPage:
        if await self.get_product(tenant_id, product_id) is None:
            raise CatalogAdminNotFound
        after = decode_cursor(cursor, 2)
        rows = await self._pool.pool.fetch(
            """SELECT * FROM inventory_movements WHERE tenant_id=$1 AND product_id=$2
               AND ($3::text IS NULL OR movement_type=$3)
               AND ($4::timestamptz IS NULL OR created_at >= $4)
               AND ($5::timestamptz IS NULL OR created_at <= $5)
               AND ($6::timestamptz IS NULL OR (created_at,id) < ($6,$7::uuid))
               ORDER BY created_at DESC,id DESC LIMIT $8""",
            tenant_id, product_id, movement_type.value if movement_type else None,
            created_from, created_to, datetime.fromisoformat(after[0]) if after else None,
            UUID(after[1]) if after else None, limit + 1,
        )
        items = tuple(self._to_movement(row) for row in rows[:limit])
        next_cursor = encode_cursor([rows[limit-1]["created_at"].isoformat(), rows[limit-1]["id"]]) if len(rows) > limit else None
        return InventoryMovementPage(items=items, next_cursor=next_cursor)

    async def summary(self, tenant_id: UUID, limit: int = 5) -> InventorySummary:
        counts = await self._pool.pool.fetchrow(
            """SELECT count(*) FILTER (WHERE p.status='ACTIVE') active_products,
               count(*) FILTER (WHERE p.status='INACTIVE') inactive_products,
               count(*) FILTER (WHERE p.status='ACTIVE' AND p.low_stock_threshold IS NOT NULL AND b.on_hand_quantity-b.reserved_quantity<=p.low_stock_threshold) low_stock_products,
               count(*) FILTER (WHERE p.status='ACTIVE' AND b.on_hand_quantity-b.reserved_quantity=0) out_of_stock_products
               FROM products p JOIN inventory_balances b ON b.tenant_id=p.tenant_id AND b.product_id=p.id WHERE p.tenant_id=$1""", tenant_id,
        )
        page = await self.list_products(tenant_id, status=ProductStatus.ACTIVE, category_id=None, query=None, stock_state=StockState.LOW, limit=limit, cursor=None)
        return InventorySummary(**dict(counts), oldest_low_stock_products=page.items)

    async def reconciliation_failures(self, limit: int) -> tuple[tuple[str, UUID, UUID], ...]:
        rows = await self._pool.pool.fetch(
            """WITH ledger AS (
                 SELECT tenant_id,product_id,sum(on_hand_delta) on_hand,sum(reserved_delta) reserved
                 FROM inventory_movements GROUP BY tenant_id,product_id
               ), active_reservations AS (
                 SELECT p.tenant_id,r.product_id,sum(r.quantity) reserved
                 FROM inventory_reservations r JOIN products p ON p.id=r.product_id
                 WHERE r.status='ACTIVE' GROUP BY p.tenant_id,r.product_id
               ), movement_chain AS (
                 SELECT tenant_id,product_id,on_hand_before,reserved_before,
                   lag(on_hand_after) OVER (PARTITION BY tenant_id,product_id ORDER BY created_at,id) previous_on_hand,
                   lag(reserved_after) OVER (PARTITION BY tenant_id,product_id ORDER BY created_at,id) previous_reserved
                 FROM inventory_movements)
               SELECT 'balance_ledger' category,b.tenant_id,b.product_id
               FROM inventory_balances b LEFT JOIN ledger l USING (tenant_id,product_id)
               WHERE coalesce(l.on_hand,0)<>b.on_hand_quantity OR coalesce(l.reserved,0)<>b.reserved_quantity
               UNION ALL SELECT 'reservation_balance',b.tenant_id,b.product_id
               FROM inventory_balances b LEFT JOIN active_reservations r USING (tenant_id,product_id)
               WHERE coalesce(r.reserved,0)<>b.reserved_quantity
               UNION ALL SELECT 'movement_chain',tenant_id,product_id FROM movement_chain
               WHERE previous_on_hand IS NOT NULL AND (previous_on_hand<>on_hand_before OR previous_reserved<>reserved_before)
               LIMIT $1""", limit,
        )
        return tuple((row["category"], row["tenant_id"], row["product_id"]) for row in rows)

    async def _claim_idempotency(self, connection, tenant_id, staff_id, key, operation, request_hash, resource_id):
        inserted = await connection.fetchval(
            """INSERT INTO staff_api_idempotency
               (id,tenant_id,staff_id,idempotency_key,operation,request_hash,resource_id,created_at,expires_at)
               VALUES ($1,$2,$3,$4,$5,$6,$7,now(),$8)
               ON CONFLICT (tenant_id,staff_id,idempotency_key) DO NOTHING RETURNING id""",
            uuid4(), tenant_id, staff_id, key, operation, request_hash, resource_id,
            datetime.now(timezone.utc) + timedelta(hours=self._retention_hours),
        )
        if inserted:
            return None
        existing = await connection.fetchrow("SELECT request_hash,response_body FROM staff_api_idempotency WHERE tenant_id=$1 AND staff_id=$2 AND idempotency_key=$3", tenant_id, staff_id, key)
        if existing is None or existing["request_hash"] != request_hash:
            raise CatalogAdminConflict("idempotency_key_conflict")
        if existing["response_body"] is None:
            raise CatalogAdminConflict("temporarily_unavailable")
        return existing["response_body"]

    @staticmethod
    async def _finish_idempotency(connection, tenant_id, staff_id, key, body):
        await connection.execute("UPDATE staff_api_idempotency SET response_status=200,response_body=$4::jsonb WHERE tenant_id=$1 AND staff_id=$2 AND idempotency_key=$3", tenant_id, staff_id, key, json.dumps(body))

    @staticmethod
    async def _authorize(connection, tenant_id, staff_id):
        allowed = await connection.fetchval("""SELECT EXISTS(SELECT 1 FROM staff_tenant_memberships m JOIN staff_accounts a ON a.id=m.staff_id WHERE m.tenant_id=$1 AND m.staff_id=$2 AND m.active=true AND m.role='ADMIN' AND a.status='ACTIVE')""", tenant_id, staff_id)
        if not allowed:
            raise CatalogAdminAccessDenied

    @staticmethod
    async def _validate_category(connection, tenant_id, category_id):
        if category_id is not None and not await connection.fetchval("SELECT EXISTS(SELECT 1 FROM product_categories WHERE tenant_id=$1 AND id=$2 AND active=true)", tenant_id, category_id):
            raise CatalogAdminNotFound

    async def _get_locked_product(self, connection, tenant_id, product_id):
        row = await connection.fetchrow(self._product_sql() + " WHERE p.tenant_id=$1 AND p.id=$2 FOR UPDATE OF p,b", tenant_id, product_id)
        if row is None:
            raise CatalogAdminNotFound
        return self._to_product(row)

    async def _replay_product(self, connection, tenant_id, body):
        return await self._get_locked_product(connection, tenant_id, UUID(body["resource_id"]))

    @staticmethod
    def _product_sql():
        return """SELECT p.*,c.name AS category_name,b.on_hand_quantity,b.reserved_quantity,b.version AS inventory_version,b.updated_at AS inventory_updated_at FROM products p JOIN inventory_balances b ON b.tenant_id=p.tenant_id AND b.product_id=p.id LEFT JOIN product_categories c ON c.tenant_id=p.tenant_id AND c.id=p.category_id"""

    @staticmethod
    def _to_product(row) -> ProductWithInventory:
        values = dict(row)
        product = AdminProduct.model_validate({name: values[name] for name in AdminProduct.model_fields if name in values})
        sellable = row["on_hand_quantity"] - row["reserved_quantity"]
        states: list[StockState] = []
        if product.status == ProductStatus.ACTIVE and sellable == 0:
            states.append(StockState.OUT)
        if product.status == ProductStatus.ACTIVE and sellable > 0:
            states.append(StockState.AVAILABLE)
        if product.status == ProductStatus.ACTIVE and product.low_stock_threshold is not None and sellable <= product.low_stock_threshold:
            states.append(StockState.LOW)
        return ProductWithInventory(product=product, on_hand_quantity=row["on_hand_quantity"], reserved_quantity=row["reserved_quantity"], sellable_quantity=sellable, inventory_version=row["inventory_version"], inventory_updated_at=row["inventory_updated_at"], stock_states=tuple(states), permitted_actions=("EDIT", "CHANGE_STATUS", "ADJUST_INVENTORY", "VIEW_MOVEMENTS"))

    @staticmethod
    def _to_movement(row) -> InventoryMovement:
        return InventoryMovement.model_validate(dict(row))

    @staticmethod
    def _json(value):
        if isinstance(value, (Decimal, UUID)):
            return str(value)
        if hasattr(value, "value"):
            return value.value
        return value

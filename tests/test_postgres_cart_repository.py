from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from uuid import uuid4

import asyncpg
import pytest

from infrastructure.database.repositories import (
    PostgresCartRepository,
    PostgresOrderRepository,
)

TEST_POSTGRES_DSN = os.getenv("TEST_POSTGRES_DSN")
pytestmark = pytest.mark.skipif(
    TEST_POSTGRES_DSN is None,
    reason="TEST_POSTGRES_DSN is required for PostgreSQL integration tests",
)


class PoolAdapter:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool


@pytest.mark.asyncio
async def test_postgres_cart_creation_replacement_constraint_and_restart() -> None:
    assert TEST_POSTGRES_DSN is not None
    pool = await asyncpg.create_pool(TEST_POSTGRES_DSN, min_size=1, max_size=4)
    tenant_id = uuid4()
    conversation_id = uuid4()
    product_id = uuid4()
    try:
        await pool.execute(
            """
            INSERT INTO products (
                id, tenant_id, sku, name, price, currency, unit, available,
                stock_quantity, created_at, updated_at
            ) VALUES ($1, $2, $3, 'Test Chicken', 10, 'INR', 'kg', TRUE,
                      100, now(), now())
            """,
            product_id,
            tenant_id,
            f"test-{product_id}",
        )
        repository = PostgresCartRepository(PoolAdapter(pool))  # type: ignore[arg-type]

        carts = await asyncio.gather(
            *(
                repository.get_or_create_active_cart(tenant_id, conversation_id)
                for _ in range(4)
            )
        )
        assert len({cart.id for cart in carts}) == 1

        first = await repository.add_or_replace_item(
            carts[0].id, product_id, Decimal(2)
        )
        replaced = await repository.add_or_replace_item(
            carts[0].id, product_id, Decimal("3.5")
        )
        assert len(first.items) == len(replaced.items) == 1
        assert replaced.items[0].quantity == Decimal("3.5")

        with pytest.raises(asyncpg.CheckViolationError):
            await repository.add_or_replace_item(
                carts[0].id, product_id, Decimal(0)
            )

        restarted_repository = PostgresCartRepository(
            PoolAdapter(pool)  # type: ignore[arg-type]
        )
        restored = await restarted_repository.get_active_cart(
            tenant_id, conversation_id
        )
        assert restored is not None
        assert restored.items == replaced.items
    finally:
        await pool.execute("DELETE FROM carts WHERE tenant_id = $1", tenant_id)
        await pool.execute("DELETE FROM products WHERE id = $1", product_id)
        await pool.close()


@pytest.mark.asyncio
async def test_postgres_order_confirmation_is_idempotent_and_snapshots_cart() -> None:
    assert TEST_POSTGRES_DSN is not None
    pool = await asyncpg.create_pool(TEST_POSTGRES_DSN, min_size=1, max_size=4)
    tenant_id = uuid4()
    conversation_id = uuid4()
    product_id = uuid4()
    try:
        await pool.execute(
            """
            INSERT INTO products (
                id, tenant_id, sku, name, price, currency, unit, available,
                stock_quantity, created_at, updated_at
            ) VALUES ($1, $2, $3, 'Snapshot Chicken', 320, 'INR', 'kg', TRUE,
                      100, now(), now())
            """,
            product_id,
            tenant_id,
            f"order-test-{product_id}",
        )
        adapter = PoolAdapter(pool)
        cart_repository = PostgresCartRepository(adapter)  # type: ignore[arg-type]
        cart = await (
            cart_repository.get_or_create_active_cart_and_add_or_replace_item(
                tenant_id, conversation_id, product_id, Decimal(2)
            )
        )
        order_repository = PostgresOrderRepository(adapter)  # type: ignore[arg-type]

        first = await order_repository.create_confirmed_order_from_cart(
            conversation_id,
            cart.id,
            "Samad",
            "9876543210",
            "12 Market Road",
        )
        retried = await order_repository.create_confirmed_order_from_cart(
            conversation_id,
            cart.id,
            "Samad",
            "9876543210",
            "12 Market Road",
        )
        await pool.execute(
            "UPDATE products SET name = 'Changed', price = 999 WHERE id = $1",
            product_id,
        )
        latest = await order_repository.get_latest_order(conversation_id)

        assert first.id == retried.id
        assert latest is not None
        assert latest.items[0].product_name == "Snapshot Chicken"
        assert latest.items[0].unit_price == Decimal(320)
        assert await cart_repository.get_active_cart(tenant_id, conversation_id) is None
        next_cart = await cart_repository.get_or_create_active_cart(
            tenant_id, conversation_id
        )
        assert next_cart.id != cart.id
    finally:
        await pool.execute(
            "DELETE FROM orders WHERE conversation_id = $1", conversation_id
        )
        await pool.execute("DELETE FROM carts WHERE tenant_id = $1", tenant_id)
        await pool.execute("DELETE FROM products WHERE id = $1", product_id)
        await pool.close()


@pytest.mark.asyncio
async def test_postgres_order_and_cart_closure_roll_back_together() -> None:
    assert TEST_POSTGRES_DSN is not None
    pool = await asyncpg.create_pool(TEST_POSTGRES_DSN, min_size=1, max_size=4)
    tenant_id = uuid4()
    conversation_id = uuid4()
    product_id = uuid4()
    suffix = uuid4().hex
    function_name = f"fail_cart_close_{suffix}"
    trigger_name = f"fail_cart_close_trigger_{suffix}"
    try:
        await pool.execute(
            """
            INSERT INTO products (
                id, tenant_id, sku, name, price, currency, unit, available,
                stock_quantity, created_at, updated_at
            ) VALUES ($1, $2, $3, 'Rollback Chicken', 320, 'INR', 'kg', TRUE,
                      100, now(), now())
            """,
            product_id,
            tenant_id,
            f"rollback-test-{product_id}",
        )
        adapter = PoolAdapter(pool)
        cart_repository = PostgresCartRepository(adapter)  # type: ignore[arg-type]
        cart = await (
            cart_repository.get_or_create_active_cart_and_add_or_replace_item(
                tenant_id, conversation_id, product_id, Decimal(2)
            )
        )
        await pool.execute(
            f"""
            CREATE FUNCTION {function_name}() RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'forced cart closure failure';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        await pool.execute(
            f"""
            CREATE TRIGGER {trigger_name}
            BEFORE UPDATE ON carts
            FOR EACH ROW
            WHEN (NEW.id = '{cart.id}'::uuid AND NEW.status = 'CHECKED_OUT')
            EXECUTE FUNCTION {function_name}()
            """
        )
        order_repository = PostgresOrderRepository(adapter)  # type: ignore[arg-type]

        with pytest.raises(asyncpg.RaiseError, match="forced cart closure failure"):
            await order_repository.create_confirmed_order_from_cart(
                conversation_id,
                cart.id,
                "Samad",
                "9876543210",
                "12 Market Road",
            )

        assert await order_repository.get_latest_order(conversation_id) is None
        assert await cart_repository.get_active_cart(tenant_id, conversation_id)
    finally:
        await pool.execute(f"DROP TRIGGER IF EXISTS {trigger_name} ON carts")
        await pool.execute(f"DROP FUNCTION IF EXISTS {function_name}()")
        await pool.execute(
            "DELETE FROM orders WHERE conversation_id = $1", conversation_id
        )
        await pool.execute("DELETE FROM carts WHERE tenant_id = $1", tenant_id)
        await pool.execute("DELETE FROM products WHERE id = $1", product_id)
        await pool.close()

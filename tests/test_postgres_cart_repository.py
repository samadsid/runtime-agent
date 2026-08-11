from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from uuid import uuid4

import asyncpg
import pytest

from commerce.models import (
    FulfilmentActor,
    FulfilmentActorType,
    OrderConfirmed,
    OrderStatus,
    StockUnavailable,
)
from commerce.repositories import (
    CartNotFoundError,
    StaleCartError,
)
from commerce.services import FulfilmentService
from infrastructure.database.repositories import (
    PostgresCartRepository,
    PostgresFulfilmentUnitOfWork,
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
        await pool.execute(
            """
            INSERT INTO inventory_balances (
                product_id, on_hand_quantity, reserved_quantity, updated_at
            ) VALUES ($1, 100, 0, now())
            """,
            product_id,
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
        assert first.version == 1
        assert replaced.version == 2
        assert replaced.items[0].quantity == Decimal("3.5")

        unchanged = await repository.update_item_quantity_by_ordinal(
            tenant_id, conversation_id, 1, Decimal("3.5")
        )
        assert unchanged.version == replaced.version

        updated = await repository.update_item_quantity_by_ordinal(
            tenant_id, conversation_id, 1, Decimal(4)
        )
        assert updated.version == replaced.version + 1
        assert updated.items[0].quantity == Decimal(4)

        with pytest.raises(StaleCartError):
            await repository.clear_active_cart(
                tenant_id,
                conversation_id,
                updated.id,
                expected_version=replaced.version,
            )
        preserved = await repository.get_active_cart(tenant_id, conversation_id)
        assert preserved is not None
        assert preserved.items == updated.items
        assert preserved.version == updated.version

        with pytest.raises(CartNotFoundError):
            await repository.clear_active_cart(
                uuid4(),
                conversation_id,
                updated.id,
                expected_version=updated.version,
            )

        with pytest.raises(asyncpg.CheckViolationError):
            await repository.update_item_quantity_by_ordinal(
                tenant_id, conversation_id, 1, Decimal(0)
            )
        rolled_back = await repository.get_active_cart(tenant_id, conversation_id)
        assert rolled_back is not None
        assert rolled_back.items == updated.items
        assert rolled_back.version == updated.version

        with pytest.raises(asyncpg.CheckViolationError):
            await repository.add_or_replace_item(carts[0].id, product_id, Decimal(0))

        cleared = await repository.clear_active_cart(
            tenant_id,
            conversation_id,
            updated.id,
            expected_version=updated.version,
        )
        assert cleared.items == ()
        assert cleared.version == updated.version + 1

        restarted_repository = PostgresCartRepository(
            PoolAdapter(pool)  # type: ignore[arg-type]
        )
        restored = await restarted_repository.get_active_cart(
            tenant_id, conversation_id
        )
        assert restored is not None
        assert restored.id == cleared.id
        assert restored.items == ()
        assert restored.version == cleared.version
    finally:
        await pool.execute("DELETE FROM carts WHERE tenant_id = $1", tenant_id)
        await pool.execute(
            "DELETE FROM inventory_balances WHERE product_id = $1", product_id
        )
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
        await pool.execute(
            """
            INSERT INTO inventory_balances (
                product_id, on_hand_quantity, reserved_quantity, updated_at
            ) VALUES ($1, 100, 0, now())
            """,
            product_id,
        )
        adapter = PoolAdapter(pool)
        cart_repository = PostgresCartRepository(adapter)  # type: ignore[arg-type]
        cart = await cart_repository.get_or_create_active_cart_and_add_or_replace_item(
            tenant_id, conversation_id, product_id, Decimal(2)
        )
        order_repository = PostgresOrderRepository(adapter)  # type: ignore[arg-type]

        first = await order_repository.create_confirmed_order_from_cart(
            tenant_id,
            conversation_id,
            cart.id,
            cart.version,
            "Samad",
            "9876543210",
            "12 Market Road",
        )
        retried = await order_repository.create_confirmed_order_from_cart(
            tenant_id,
            conversation_id,
            cart.id,
            cart.version,
            "Samad",
            "9876543210",
            "12 Market Road",
        )
        await pool.execute(
            "UPDATE products SET name = 'Changed', price = 999 WHERE id = $1",
            product_id,
        )
        latest = await order_repository.get_latest_order(conversation_id)

        assert isinstance(first, OrderConfirmed)
        assert isinstance(retried, OrderConfirmed)
        assert first.order.id == retried.order.id
        balance = await pool.fetchrow(
            """
            SELECT on_hand_quantity, reserved_quantity
            FROM inventory_balances WHERE product_id = $1
            """,
            product_id,
        )
        reservation_count = await pool.fetchval(
            "SELECT COUNT(*) FROM inventory_reservations WHERE order_id = $1",
            first.order.id,
        )
        history_count = await pool.fetchval(
            "SELECT COUNT(*) FROM order_status_history WHERE order_id = $1",
            first.order.id,
        )
        assert balance["reserved_quantity"] == Decimal(2)
        assert reservation_count == 1
        assert history_count == 1
        assert latest is not None
        assert latest.items[0].product_name == "Snapshot Chicken"
        assert latest.items[0].unit_price == Decimal(320)
        assert await cart_repository.get_active_cart(tenant_id, conversation_id) is None
        fulfilment = FulfilmentService(
            lambda: PostgresFulfilmentUnitOfWork(adapter)  # type: ignore[arg-type]
        )
        cancelled = await fulfilment.transition_order(
            first.order.id,
            OrderStatus.CANCELLED,
            FulfilmentActor(actor_id=uuid4(), actor_type=FulfilmentActorType.STAFF),
            "Integration test",
        )
        cancelled_again = await fulfilment.transition_order(
            first.order.id,
            OrderStatus.CANCELLED,
            FulfilmentActor(actor_id=uuid4(), actor_type=FulfilmentActorType.STAFF),
        )
        assert cancelled == cancelled_again
        assert (
            await pool.fetchval(
                "SELECT reserved_quantity FROM inventory_balances WHERE product_id = $1",
                product_id,
            )
            == 0
        )
        assert (
            await pool.fetchval(
                "SELECT COUNT(*) FROM order_status_history WHERE order_id = $1",
                first.order.id,
            )
            == 2
        )
        next_cart = await cart_repository.get_or_create_active_cart(
            tenant_id, conversation_id
        )
        assert next_cart.id != cart.id
    finally:
        await pool.execute(
            "DELETE FROM orders WHERE conversation_id = $1", conversation_id
        )
        await pool.execute("DELETE FROM carts WHERE tenant_id = $1", tenant_id)
        await pool.execute(
            "DELETE FROM inventory_balances WHERE product_id = $1", product_id
        )
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
        await pool.execute(
            """
            INSERT INTO inventory_balances (
                product_id, on_hand_quantity, reserved_quantity, updated_at
            ) VALUES ($1, 100, 0, now())
            """,
            product_id,
        )
        adapter = PoolAdapter(pool)
        cart_repository = PostgresCartRepository(adapter)  # type: ignore[arg-type]
        cart = await cart_repository.get_or_create_active_cart_and_add_or_replace_item(
            tenant_id, conversation_id, product_id, Decimal(2)
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
                tenant_id,
                conversation_id,
                cart.id,
                cart.version,
                "Samad",
                "9876543210",
                "12 Market Road",
            )

        assert await order_repository.get_latest_order(conversation_id) is None
        assert await cart_repository.get_active_cart(tenant_id, conversation_id)
        assert (
            await pool.fetchval(
                "SELECT reserved_quantity FROM inventory_balances WHERE product_id = $1",
                product_id,
            )
            == 0
        )
    finally:
        await pool.execute(f"DROP TRIGGER IF EXISTS {trigger_name} ON carts")
        await pool.execute(f"DROP FUNCTION IF EXISTS {function_name}()")
        await pool.execute(
            "DELETE FROM orders WHERE conversation_id = $1", conversation_id
        )
        await pool.execute("DELETE FROM carts WHERE tenant_id = $1", tenant_id)
        await pool.execute(
            "DELETE FROM inventory_balances WHERE product_id = $1", product_id
        )
        await pool.execute("DELETE FROM products WHERE id = $1", product_id)
        await pool.close()


@pytest.mark.asyncio
async def test_concurrent_order_confirmations_cannot_oversell() -> None:
    assert TEST_POSTGRES_DSN is not None
    pool = await asyncpg.create_pool(TEST_POSTGRES_DSN, min_size=1, max_size=4)
    tenant_id = uuid4()
    product_id = uuid4()
    conversations = (uuid4(), uuid4())
    try:
        await pool.execute(
            """
            INSERT INTO products (
                id, tenant_id, sku, name, price, currency, unit, available,
                stock_quantity, created_at, updated_at
            ) VALUES ($1, $2, $3, 'Limited Rice', 80, 'INR', 'kg', TRUE,
                      3, now(), now())
            """,
            product_id,
            tenant_id,
            f"concurrent-test-{product_id}",
        )
        await pool.execute(
            """
            INSERT INTO inventory_balances (
                product_id, on_hand_quantity, reserved_quantity, updated_at
            ) VALUES ($1, 3, 0, now())
            """,
            product_id,
        )
        adapter = PoolAdapter(pool)
        cart_repository = PostgresCartRepository(adapter)  # type: ignore[arg-type]
        carts = await asyncio.gather(
            *(
                cart_repository.get_or_create_active_cart_and_add_or_replace_item(
                    tenant_id, conversation_id, product_id, Decimal(2)
                )
                for conversation_id in conversations
            )
        )
        order_repository = PostgresOrderRepository(adapter)  # type: ignore[arg-type]

        results = await asyncio.gather(
            *(
                order_repository.create_confirmed_order_from_cart(
                    tenant_id,
                    conversation_id,
                    cart.id,
                    cart.version,
                    "Customer",
                    "9876543210",
                    "12 Market Road",
                )
                for conversation_id, cart in zip(conversations, carts, strict=True)
            ),
            return_exceptions=True,
        )

        assert sum(isinstance(result, OrderConfirmed) for result in results) == 1
        assert sum(isinstance(result, StockUnavailable) for result in results) == 1
        assert await pool.fetchval(
            "SELECT reserved_quantity FROM inventory_balances WHERE product_id = $1",
            product_id,
        ) == Decimal(2)
    finally:
        await pool.execute(
            "DELETE FROM orders WHERE conversation_id = ANY($1::uuid[])", conversations
        )
        await pool.execute("DELETE FROM carts WHERE tenant_id = $1", tenant_id)
        await pool.execute(
            "DELETE FROM inventory_balances WHERE product_id = $1", product_id
        )
        await pool.execute("DELETE FROM products WHERE id = $1", product_id)
        await pool.close()

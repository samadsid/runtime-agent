from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

import asyncpg

from commerce.models import (
    OnlinePaymentReady,
    OrderStatus,
    PaymentAttempt,
    PaymentAttemptStatus,
    ProviderPaymentStatus,
    StaleCheckout,
    StaleCheckoutReason,
    StockShortage,
    StockUnavailable,
    VerifiedPaymentEvent,
)
from commerce.repositories import PaymentRepository
from infrastructure.database import DatabasePool
from infrastructure.database.public_order_numbers import allocate_public_order_number

from .postgres_notification_outbox_repository import (
    PostgresNotificationOutboxRepository,
)
from .postgres_order_repository import PostgresOrderRepository


class PostgresPaymentRepository(PaymentRepository):
    def __init__(
        self,
        pool: DatabasePool,
        *,
        public_order_prefix: str = "MU",
        business_timezone: str = "Asia/Kolkata",
    ) -> None:
        self._pool = pool
        self._public_order_prefix = public_order_prefix
        self._business_timezone = business_timezone

    async def create_provisional_order(
        self,
        *,
        tenant_id: UUID,
        conversation_id: UUID,
        cart_id: UUID,
        expected_cart_version: int,
        customer_name: str,
        phone_number: str,
        delivery_address: str,
        provider: str,
        expires_at: datetime,
        idempotency_key: str,
    ):
        async with self._pool.pool.acquire() as connection, connection.transaction():
            existing_id = await connection.fetchval(
                """SELECT o.id FROM orders o JOIN carts c ON c.id=o.source_cart_id
                   WHERE o.source_cart_id=$1 AND c.tenant_id=$2 AND c.conversation_id=$3""",
                cart_id,
                tenant_id,
                conversation_id,
            )
            if existing_id:
                attempt = await self._latest_attempt_for_order(
                    connection, tenant_id, existing_id
                )
                if attempt is None:
                    raise RuntimeError("Existing online order has no payment attempt.")
                return OnlinePaymentReady(
                    order=await PostgresOrderRepository._load_order(
                        connection, existing_id
                    ),
                    attempt=attempt,
                    idempotent=True,
                )
            cart = await connection.fetchrow(
                "SELECT id, tenant_id, conversation_id, status, version FROM carts WHERE id=$1 FOR UPDATE",
                cart_id,
            )
            if (
                cart is None
                or cart["tenant_id"] != tenant_id
                or cart["conversation_id"] != conversation_id
                or cart["status"] != "ACTIVE"
            ):
                return StaleCheckout(
                    cart_id=cart_id, reason=StaleCheckoutReason.CART_UNAVAILABLE
                )
            if cart["version"] != expected_cart_version:
                return StaleCheckout(
                    cart_id=cart_id, reason=StaleCheckoutReason.CART_CHANGED
                )
            rows = await connection.fetch(
                """SELECT ci.product_id, ci.quantity, p.name product_name, p.unit,
                          p.price unit_price, p.currency
                   FROM cart_items ci JOIN products p ON p.id=ci.product_id AND p.tenant_id=$2
                   WHERE ci.cart_id=$1 ORDER BY ci.created_at, ci.id""",
                cart_id,
                tenant_id,
            )
            if not rows:
                return StaleCheckout(
                    cart_id=cart_id, reason=StaleCheckoutReason.EMPTY_CART
                )
            currencies = {row["currency"] for row in rows}
            if len(currencies) != 1:
                raise ValueError("A payment order must use one currency.")
            product_ids = sorted((row["product_id"] for row in rows), key=str)
            balances = await connection.fetch(
                """SELECT product_id, on_hand_quantity, reserved_quantity
                   FROM inventory_balances WHERE product_id=ANY($1::uuid[])
                   ORDER BY product_id FOR UPDATE""",
                product_ids,
            )
            by_product = {row["product_id"]: row for row in balances}
            shortages = tuple(
                StockShortage(
                    product_id=row["product_id"],
                    product_name=row["product_name"],
                    unit=row["unit"],
                    requested_quantity=row["quantity"],
                    available_quantity=(
                        by_product[row["product_id"]]["on_hand_quantity"]
                        - by_product[row["product_id"]]["reserved_quantity"]
                        if row["product_id"] in by_product
                        else Decimal(0)
                    ),
                )
                for row in rows
                if row["product_id"] not in by_product
                or row["quantity"]
                > by_product[row["product_id"]]["on_hand_quantity"]
                - by_product[row["product_id"]]["reserved_quantity"]
            )
            if shortages:
                return StockUnavailable(
                    cart_id=cart_id, cart_version=cart["version"], shortages=shortages
                )
            order_id, attempt_id = uuid4(), uuid4()
            public_order_number = await allocate_public_order_number(
                connection,
                prefix=self._public_order_prefix,
                business_timezone=self._business_timezone,
            )
            await connection.execute(
                """INSERT INTO orders (id,tenant_id,public_order_number,source_cart_id,conversation_id,status,payment_method,
                   customer_name,phone_number,delivery_address,created_at,confirmed_at)
                   VALUES ($1,$2,$3,$4,$5,'AWAITING_PAYMENT','ONLINE',$6,$7,$8,now(),NULL)""",
                order_id,
                tenant_id,
                public_order_number,
                cart_id,
                conversation_id,
                customer_name,
                phone_number,
                delivery_address,
            )
            item_values = []
            for row in rows:
                item_values.append(
                    (
                        uuid4(),
                        order_id,
                        row["product_id"],
                        row["product_name"],
                        row["unit"],
                        row["unit_price"],
                        row["currency"],
                        row["quantity"],
                    )
                )
            await connection.executemany(
                "INSERT INTO order_items (id,order_id,product_id,product_name,unit,unit_price,currency,quantity) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
                item_values,
            )
            await connection.executemany(
                "UPDATE inventory_balances SET reserved_quantity=reserved_quantity+$2,updated_at=now() WHERE product_id=$1",
                [(row["product_id"], row["quantity"]) for row in rows],
            )
            await connection.executemany(
                "INSERT INTO inventory_reservations (id,order_id,product_id,quantity,status,created_at) VALUES ($1,$2,$3,$4,'ACTIVE',now())",
                [
                    (uuid4(), order_id, row["product_id"], row["quantity"])
                    for row in rows
                ],
            )
            await connection.execute(
                "UPDATE carts SET status='CHECKED_OUT',updated_at=now() WHERE id=$1",
                cart_id,
            )
            await connection.execute(
                "INSERT INTO order_status_history (id,order_id,from_status,to_status,actor_id,actor_type,reason,created_at) VALUES ($1,$2,NULL,'AWAITING_PAYMENT',NULL,'CUSTOMER',NULL,now())",
                uuid4(),
                order_id,
            )
            amount = sum(
                (row["unit_price"] * row["quantity"] for row in rows), Decimal(0)
            )
            await connection.execute(
                """INSERT INTO payment_attempts (id,tenant_id,order_id,provider,idempotency_key,amount,currency,status,expires_at,created_at,updated_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,'CREATING',$8,now(),now())""",
                attempt_id,
                tenant_id,
                order_id,
                provider,
                idempotency_key,
                amount,
                next(iter(currencies)),
                expires_at,
            )
            return OnlinePaymentReady(
                order=await PostgresOrderRepository._load_order(connection, order_id),
                attempt=await self._load_attempt(connection, attempt_id),
            )

    async def persist_provider_checkout(
        self, attempt_id, provider_payment_id, checkout_url, expires_at
    ):
        async with self._pool.pool.acquire() as connection, connection.transaction():
            row = await connection.fetchrow(
                "SELECT status,order_id FROM payment_attempts WHERE id=$1 FOR UPDATE",
                attempt_id,
            )
            if row is None:
                raise LookupError("Payment attempt not found.")
            if row["status"] == "CREATING":
                await connection.execute(
                    "UPDATE payment_attempts SET provider_payment_id=$2,checkout_url=$3,expires_at=$4,status='PENDING',updated_at=now() WHERE id=$1",
                    attempt_id,
                    provider_payment_id,
                    checkout_url,
                    expires_at,
                )
            return OnlinePaymentReady(
                order=await PostgresOrderRepository._load_order(
                    connection, row["order_id"]
                ),
                attempt=await self._load_attempt(connection, attempt_id),
                idempotent=row["status"] != "CREATING",
            )

    async def fail_creation(self, attempt_id: UUID, failure_code: str) -> None:
        async with self._pool.pool.acquire() as connection, connection.transaction():
            row = await connection.fetchrow(
                "SELECT order_id,status FROM payment_attempts WHERE id=$1 FOR UPDATE",
                attempt_id,
            )
            if row and row["status"] == "CREATING":
                await self._release(connection, row["order_id"])
                await connection.execute(
                    "UPDATE payment_attempts SET status='FAILED',failure_code=$2,updated_at=now() WHERE id=$1",
                    attempt_id,
                    failure_code,
                )
                await self._transition(
                    connection,
                    row["order_id"],
                    OrderStatus.PAYMENT_FAILED,
                    "provider_creation_failed",
                )

    async def get_attempt(self, attempt_id: UUID) -> PaymentAttempt:
        async with self._pool.pool.acquire() as connection:
            return await self._load_attempt(connection, attempt_id)

    async def get_latest_attempt(self, tenant_id, conversation_id, order_id=None):
        async with self._pool.pool.acquire() as connection:
            if order_id is None:
                order_id = await connection.fetchval(
                    """SELECT o.id FROM orders o JOIN carts c ON c.id=o.source_cart_id
                       WHERE c.tenant_id=$1 AND c.conversation_id=$2 AND o.payment_method='ONLINE'
                       ORDER BY o.created_at DESC,o.id DESC LIMIT 1""",
                    tenant_id,
                    conversation_id,
                )
            if order_id is None or not await self._owned(
                connection, tenant_id, conversation_id, order_id
            ):
                return None
            return await self._latest_attempt_for_order(connection, tenant_id, order_id)

    async def create_retry_attempt(
        self,
        tenant_id,
        conversation_id,
        provider,
        expires_at,
        idempotency_key,
        order_id=None,
    ):
        async with self._pool.pool.acquire() as connection, connection.transaction():
            order_id = order_id or await self._latest_online_order_id(
                connection, tenant_id, conversation_id
            )
            if order_id is None or not await self._owned(
                connection, tenant_id, conversation_id, order_id
            ):
                raise LookupError("Eligible payment order not found.")
            order = await PostgresOrderRepository._load_order(connection, order_id)
            if order.status not in {
                OrderStatus.PAYMENT_FAILED,
                OrderStatus.PAYMENT_EXPIRED,
                OrderStatus.AWAITING_PAYMENT,
            }:
                raise ValueError("Order is not eligible for online payment retry.")
            latest = await self._latest_attempt_for_order(
                connection, tenant_id, order_id
            )
            if (
                latest
                and latest.status == PaymentAttemptStatus.PENDING
                and latest.expires_at > datetime.now(latest.expires_at.tzinfo)
            ):
                return OnlinePaymentReady(order=order, attempt=latest, idempotent=True)
            shortages = await self._reactivate(connection, order_id)
            if shortages:
                return StockUnavailable(
                    cart_id=order.source_cart_id, cart_version=0, shortages=shortages
                )
            await self._transition(
                connection,
                order_id,
                OrderStatus.AWAITING_PAYMENT,
                "online_payment_retry",
            )
            attempt_id = uuid4()
            amount = sum(
                (item.unit_price * item.quantity for item in order.items), Decimal(0)
            )
            currencies = {item.currency for item in order.items}
            if len(currencies) != 1:
                raise ValueError("Order snapshots do not have one currency.")
            await connection.execute(
                """INSERT INTO payment_attempts (id,tenant_id,order_id,provider,idempotency_key,amount,currency,status,expires_at,created_at,updated_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,'CREATING',$8,now(),now())""",
                attempt_id,
                tenant_id,
                order_id,
                provider,
                idempotency_key,
                amount,
                next(iter(currencies)),
                expires_at,
            )
            return OnlinePaymentReady(
                order=await PostgresOrderRepository._load_order(connection, order_id),
                attempt=await self._load_attempt(connection, attempt_id),
            )

    async def switch_to_cod(self, tenant_id, conversation_id, order_id=None):
        async with self._pool.pool.acquire() as connection, connection.transaction():
            order_id = order_id or await self._latest_online_order_id(
                connection, tenant_id, conversation_id
            )
            if order_id is None or not await self._owned(
                connection, tenant_id, conversation_id, order_id
            ):
                raise LookupError("Eligible payment order not found.")
            await connection.execute(
                "SELECT id FROM orders WHERE id=$1 FOR UPDATE", order_id
            )
            if await connection.fetchval(
                "SELECT 1 FROM payment_attempts WHERE order_id=$1 AND status='SUCCEEDED'",
                order_id,
            ):
                raise ValueError("A successful payment cannot switch to COD.")
            if await connection.fetchval(
                "SELECT 1 FROM payment_attempts WHERE order_id=$1 AND status='CREATING'",
                order_id,
            ):
                raise RuntimeError("Payment status is temporarily ambiguous.")
            shortages = await self._reactivate(connection, order_id)
            if shortages:
                raise ValueError("Stock is no longer available.")
            await connection.execute(
                "UPDATE payment_attempts SET status='CANCELLED',failure_code='switched_to_cod',updated_at=now() WHERE order_id=$1 AND status='PENDING'",
                order_id,
            )
            await connection.execute(
                """UPDATE orders SET payment_method='CASH_ON_DELIVERY',confirmed_at=now(),
                          version=version+1,updated_at=now() WHERE id=$1""",
                order_id,
            )
            await self._transition(
                connection,
                order_id,
                OrderStatus.CONFIRMED,
                "switched_to_cash_on_delivery",
            )
            return await PostgresOrderRepository._load_order(connection, order_id)

    async def process_event(self, event: VerifiedPaymentEvent, payload_hash: str):
        async with self._pool.pool.acquire() as connection, connection.transaction():
            inserted = await connection.fetchval(
                """INSERT INTO payment_webhook_events (id,provider,provider_event_id,provider_payment_id,event_type,amount,currency,payload_hash,processing_status,received_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'RECEIVED',now())
                   ON CONFLICT (provider,provider_event_id) DO NOTHING RETURNING id""",
                uuid4(),
                event.provider,
                event.provider_event_id,
                event.provider_payment_id,
                event.status.value,
                event.amount,
                event.currency,
                payload_hash,
            )
            if inserted is None:
                return None
            row = await connection.fetchrow(
                "SELECT * FROM payment_attempts WHERE provider=$1 AND provider_payment_id=$2 FOR UPDATE",
                event.provider,
                event.provider_payment_id,
            )
            if row is None:
                await self._finish_event(
                    connection, inserted, "QUARANTINED", "unknown_payment"
                )
                return None
            attempt = self._attempt(row)
            await connection.execute(
                "SELECT id FROM orders WHERE id=$1 FOR UPDATE", attempt.order_id
            )
            if attempt.amount != event.amount or attempt.currency != event.currency:
                await self._finish_event(
                    connection, inserted, "REJECTED", "amount_or_currency_mismatch"
                )
                return attempt
            order_status = OrderStatus(
                await connection.fetchval(
                    "SELECT status FROM orders WHERE id=$1", attempt.order_id
                )
            )
            if event.status == ProviderPaymentStatus.SUCCEEDED:
                if (
                    attempt.status == PaymentAttemptStatus.SUCCEEDED
                    or order_status == OrderStatus.CONFIRMED
                ):
                    await self._finish_event(
                        connection, inserted, "IGNORED", "already_succeeded"
                    )
                    return attempt
                shortages = await self._reactivate(connection, attempt.order_id)
                if shortages:
                    await self._finish_event(
                        connection,
                        inserted,
                        "QUARANTINED",
                        "late_success_stock_conflict",
                    )
                    return attempt
                await connection.execute(
                    "UPDATE payment_attempts SET status='SUCCEEDED',failure_code=NULL,updated_at=now() WHERE id=$1",
                    attempt.id,
                )
                await connection.execute(
                    """UPDATE orders SET confirmed_at=now(),version=version+1,
                              updated_at=now() WHERE id=$1""", attempt.order_id
                )
                await self._transition(
                    connection,
                    attempt.order_id,
                    OrderStatus.CONFIRMED,
                    "provider_payment_succeeded",
                )
                await self._finish_event(connection, inserted, "PROCESSED", None)
            elif event.status in {
                ProviderPaymentStatus.FAILED,
                ProviderPaymentStatus.EXPIRED,
                ProviderPaymentStatus.CANCELLED,
            }:
                if (
                    attempt.status == PaymentAttemptStatus.SUCCEEDED
                    or order_status == OrderStatus.CONFIRMED
                ):
                    await self._finish_event(
                        connection, inserted, "IGNORED", "terminal_success"
                    )
                    return attempt
                attempt_status = (
                    "EXPIRED"
                    if event.status == ProviderPaymentStatus.EXPIRED
                    else event.status.value
                )
                order_target = (
                    OrderStatus.PAYMENT_EXPIRED
                    if event.status == ProviderPaymentStatus.EXPIRED
                    else OrderStatus.PAYMENT_FAILED
                )
                await connection.execute(
                    "UPDATE payment_attempts SET status=$2,failure_code=$3,updated_at=now() WHERE id=$1",
                    attempt.id,
                    attempt_status,
                    event.status.value.lower(),
                )
                await self._release(connection, attempt.order_id)
                await self._transition(
                    connection,
                    attempt.order_id,
                    order_target,
                    f"provider_payment_{event.status.value.lower()}",
                )
                await self._finish_event(connection, inserted, "PROCESSED", None)
            else:
                await self._finish_event(
                    connection, inserted, "IGNORED", "non_terminal"
                )
            return await self._load_attempt(connection, attempt.id)

    async def claim_reconciliation_batch(self, limit, now):
        async with self._pool.pool.acquire() as connection, connection.transaction():
            rows = await connection.fetch(
                """SELECT * FROM payment_attempts
                   WHERE status IN ('CREATING','PENDING')
                     AND (reconcile_after IS NULL OR reconcile_after <= $1)
                   ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT $2""",
                now,
                limit,
            )
            if rows:
                await connection.execute(
                    """UPDATE payment_attempts SET reconciliation_attempts=reconciliation_attempts+1,
                       reconcile_after=$2 + (
                           LEAST(300, POWER(2, reconciliation_attempts + 1))
                           * interval '1 second'
                       ),updated_at=now() WHERE id=ANY($1::uuid[])""",
                    [row["id"] for row in rows],
                    now,
                )
            return tuple(self._attempt(row) for row in rows)

    async def _release(self, connection, order_id):
        rows = await connection.fetch(
            "SELECT product_id,quantity FROM inventory_reservations WHERE order_id=$1 AND status='ACTIVE' FOR UPDATE",
            order_id,
        )
        for row in rows:
            await connection.execute(
                "UPDATE inventory_balances SET reserved_quantity=reserved_quantity-$2,updated_at=now() WHERE product_id=$1",
                row["product_id"],
                row["quantity"],
            )
        await connection.execute(
            "UPDATE inventory_reservations SET status='RELEASED',released_at=now() WHERE order_id=$1 AND status='ACTIVE'",
            order_id,
        )

    async def _reactivate(self, connection, order_id):
        rows = await connection.fetch(
            """SELECT r.product_id,r.quantity,i.product_name,i.unit,r.status
               FROM inventory_reservations r JOIN order_items i ON i.order_id=r.order_id AND i.product_id=r.product_id
               WHERE r.order_id=$1 ORDER BY r.product_id FOR UPDATE""",
            order_id,
        )
        released = [row for row in rows if row["status"] == "RELEASED"]
        if not released:
            return ()
        balances = await connection.fetch(
            "SELECT product_id,on_hand_quantity,reserved_quantity FROM inventory_balances WHERE product_id=ANY($1::uuid[]) ORDER BY product_id FOR UPDATE",
            [row["product_id"] for row in released],
        )
        by_product = {row["product_id"]: row for row in balances}
        shortages = tuple(
            StockShortage(
                product_id=row["product_id"],
                product_name=row["product_name"],
                unit=row["unit"],
                requested_quantity=row["quantity"],
                available_quantity=(
                    by_product[row["product_id"]]["on_hand_quantity"]
                    - by_product[row["product_id"]]["reserved_quantity"]
                    if row["product_id"] in by_product
                    else Decimal(0)
                ),
            )
            for row in released
            if row["product_id"] not in by_product
            or row["quantity"]
            > by_product[row["product_id"]]["on_hand_quantity"]
            - by_product[row["product_id"]]["reserved_quantity"]
        )
        if shortages:
            return shortages
        for row in released:
            await connection.execute(
                "UPDATE inventory_balances SET reserved_quantity=reserved_quantity+$2,updated_at=now() WHERE product_id=$1",
                row["product_id"],
                row["quantity"],
            )
        await connection.execute(
            "UPDATE inventory_reservations SET status='ACTIVE',released_at=NULL WHERE order_id=$1 AND status='RELEASED'",
            order_id,
        )
        return ()

    async def _transition(self, connection, order_id, target, reason):
        current = await connection.fetchval(
            "SELECT status FROM orders WHERE id=$1", order_id
        )
        if current == target.value:
            return
        await connection.execute(
            """UPDATE orders SET status=$2,version=version+1,updated_at=now()
               WHERE id=$1""", order_id, target.value
        )
        history_id = uuid4()
        await connection.execute(
            "INSERT INTO order_status_history (id,order_id,from_status,to_status,actor_id,actor_type,reason,created_at) VALUES ($1,$2,$3,$4,NULL,'SYSTEM',$5,now())",
            history_id,
            order_id,
            current,
            target.value,
            reason,
        )
        await PostgresNotificationOutboxRepository.append_order_transition(
            connection, order_id, history_id
        )

    async def _finish_event(self, connection, event_id, status, reason):
        await connection.execute(
            "UPDATE payment_webhook_events SET processing_status=$2,failure_reason=$3,processed_at=now() WHERE id=$1",
            event_id,
            status,
            reason,
        )

    async def _owned(self, connection, tenant_id, conversation_id, order_id):
        return bool(
            await connection.fetchval(
                "SELECT 1 FROM orders o JOIN carts c ON c.id=o.source_cart_id WHERE o.id=$1 AND c.tenant_id=$2 AND c.conversation_id=$3",
                order_id,
                tenant_id,
                conversation_id,
            )
        )

    async def _latest_online_order_id(self, connection, tenant_id, conversation_id):
        return await connection.fetchval(
            "SELECT o.id FROM orders o JOIN carts c ON c.id=o.source_cart_id WHERE c.tenant_id=$1 AND c.conversation_id=$2 AND o.payment_method='ONLINE' ORDER BY o.created_at DESC,o.id DESC LIMIT 1",
            tenant_id,
            conversation_id,
        )

    async def _latest_attempt_for_order(self, connection, tenant_id, order_id):
        row = await connection.fetchrow(
            "SELECT * FROM payment_attempts WHERE tenant_id=$1 AND order_id=$2 ORDER BY created_at DESC,id DESC LIMIT 1",
            tenant_id,
            order_id,
        )
        return self._attempt(row) if row else None

    async def _load_attempt(self, connection, attempt_id):
        row = await connection.fetchrow(
            "SELECT * FROM payment_attempts WHERE id=$1", attempt_id
        )
        if row is None:
            raise LookupError("Payment attempt not found.")
        return self._attempt(row)

    @staticmethod
    def _attempt(row: asyncpg.Record) -> PaymentAttempt:
        return PaymentAttempt(
            id=row["id"],
            tenant_id=row["tenant_id"],
            order_id=row["order_id"],
            provider=row["provider"],
            provider_payment_id=row["provider_payment_id"],
            idempotency_key=row["idempotency_key"],
            amount=row["amount"],
            currency=row["currency"],
            status=PaymentAttemptStatus(row["status"]),
            checkout_url=row["checkout_url"],
            expires_at=row["expires_at"],
            failure_code=row["failure_code"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

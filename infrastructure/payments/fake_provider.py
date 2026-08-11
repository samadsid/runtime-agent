from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from commerce.models import (
    CreateProviderCheckoutRequest,
    ProviderCheckout,
    ProviderPaymentStatus,
    VerifiedPaymentEvent,
)
from commerce.payments import PaymentProviderInvalidResponseError
from infrastructure.database import DatabasePool


class FakePaymentProvider:
    def __init__(self, pool: DatabasePool, base_url: str, webhook_secret: str) -> None:
        self._pool = pool
        self._base_url = base_url.rstrip("/")
        self._secret = webhook_secret.encode()

    @property
    def name(self) -> str:
        return "fake"

    async def create_checkout(
        self, request: CreateProviderCheckoutRequest
    ) -> ProviderCheckout:
        payment_id = f"fake_{uuid4().hex}"
        row = await self._pool.pool.fetchrow(
            """
            INSERT INTO fake_provider_payments (
                provider_payment_id, idempotency_key, merchant_reference,
                amount, currency, status, expires_at, created_at, updated_at
            ) VALUES ($1,$2,$3,$4,$5,'PENDING',$6,now(),now())
            ON CONFLICT (idempotency_key) DO UPDATE
                SET idempotency_key = EXCLUDED.idempotency_key
            RETURNING provider_payment_id, status, expires_at
            """,
            payment_id,
            request.idempotency_key,
            request.merchant_reference,
            request.amount,
            request.currency,
            request.expires_at,
        )
        return ProviderCheckout(
            provider_payment_id=row["provider_payment_id"],
            status=ProviderPaymentStatus(row["status"]),
            checkout_url=f"{self._base_url}/dev/payments/{row['provider_payment_id']}",
            expires_at=row["expires_at"],
        )

    async def verify_and_parse_webhook(
        self, raw_body: bytes, signature: str
    ) -> VerifiedPaymentEvent:
        prefix = "sha256="
        if not signature.startswith(prefix):
            raise PaymentProviderInvalidResponseError("Malformed signature.")
        expected = hmac.new(self._secret, raw_body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature[len(prefix) :], expected):
            raise PaymentProviderInvalidResponseError("Invalid signature.")
        try:
            payload = json.loads(raw_body)
            return VerifiedPaymentEvent(
                provider="fake",
                provider_event_id=payload["event_id"],
                provider_payment_id=payload["payment_id"],
                status=ProviderPaymentStatus(payload["status"]),
                amount=Decimal(payload["amount"]),
                currency=payload["currency"],
                occurred_at=datetime.fromisoformat(payload["occurred_at"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise PaymentProviderInvalidResponseError(
                "Invalid webhook payload."
            ) from exc

    async def get_payment_status(
        self, provider_payment_id: str
    ) -> ProviderPaymentStatus:
        value = await self._pool.pool.fetchval(
            "SELECT status FROM fake_provider_payments WHERE provider_payment_id=$1",
            provider_payment_id,
        )
        return ProviderPaymentStatus(value) if value else ProviderPaymentStatus.UNKNOWN

    async def simulate(
        self, provider_payment_id: str, status: ProviderPaymentStatus
    ) -> tuple[bytes, str]:
        if status not in {
            ProviderPaymentStatus.SUCCEEDED,
            ProviderPaymentStatus.FAILED,
            ProviderPaymentStatus.EXPIRED,
        }:
            raise ValueError("Unsupported fake payment outcome.")
        row = await self._pool.pool.fetchrow(
            """
            UPDATE fake_provider_payments
            SET status=$2, updated_at=now()
            WHERE provider_payment_id=$1
              AND status <> 'SUCCEEDED'
            RETURNING provider_payment_id, amount, currency, status
            """,
            provider_payment_id,
            status.value,
        )
        if row is None:
            row = await self._pool.pool.fetchrow(
                "SELECT provider_payment_id, amount, currency, status FROM fake_provider_payments WHERE provider_payment_id=$1",
                provider_payment_id,
            )
        if row is None:
            raise LookupError("Fake payment does not exist.")
        payload = {
            "event_id": f"evt_{uuid4().hex}",
            "payment_id": row["provider_payment_id"],
            "status": row["status"],
            "amount": format(row["amount"], "f"),
            "currency": row["currency"],
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        }
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        signature = "sha256=" + hmac.new(self._secret, raw, hashlib.sha256).hexdigest()
        return raw, signature

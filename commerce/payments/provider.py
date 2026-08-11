from __future__ import annotations

from typing import Protocol

from commerce.models.payment import (
    CreateProviderCheckoutRequest,
    ProviderCheckout,
    ProviderPaymentStatus,
    VerifiedPaymentEvent,
)


class PaymentProviderError(RuntimeError):
    pass


class PaymentProviderTemporaryError(PaymentProviderError):
    pass


class PaymentProviderTimeoutError(PaymentProviderTemporaryError):
    pass


class PaymentProviderInvalidResponseError(PaymentProviderError):
    pass


class PaymentProviderConfigurationError(PaymentProviderError):
    pass


class PaymentProvider(Protocol):
    @property
    def name(self) -> str: ...

    async def create_checkout(
        self, request: CreateProviderCheckoutRequest
    ) -> ProviderCheckout: ...

    async def verify_and_parse_webhook(
        self, raw_body: bytes, signature: str
    ) -> VerifiedPaymentEvent: ...

    async def get_payment_status(
        self, provider_payment_id: str
    ) -> ProviderPaymentStatus: ...

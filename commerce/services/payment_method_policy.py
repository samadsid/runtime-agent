from __future__ import annotations

from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from commerce.models import Cart, PaymentMethod


class EligiblePaymentMethod(BaseModel):
    model_config = ConfigDict(frozen=True)

    method: PaymentMethod
    customer_label: str


class PaymentMethodPolicy(Protocol):
    async def eligible_methods(
        self, tenant_id: UUID, cart: Cart
    ) -> tuple[EligiblePaymentMethod, ...]: ...


class ConfiguredPaymentMethodPolicy:
    def __init__(
        self,
        enabled_methods: tuple[PaymentMethod, ...],
        *,
        online_operational: bool,
    ) -> None:
        self._enabled_methods = enabled_methods
        self._online_operational = online_operational

    async def eligible_methods(
        self, tenant_id: UUID, cart: Cart
    ) -> tuple[EligiblePaymentMethod, ...]:
        del tenant_id
        currencies = {item.product.currency for item in cart.items}
        methods: list[EligiblePaymentMethod] = []
        for method in self._enabled_methods:
            if method is PaymentMethod.ONLINE and (
                not self._online_operational or len(currencies) != 1
            ):
                continue
            methods.append(
                EligiblePaymentMethod(
                    method=method,
                    customer_label={
                        PaymentMethod.CASH_ON_DELIVERY: "Cash on Delivery",
                        PaymentMethod.ONLINE: "Online Payment",
                    }[method],
                )
            )
        return tuple(methods)

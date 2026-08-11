from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .cart import Cart
from .inventory import StockShortage
from .order import Order


class StaleCheckoutReason(str, Enum):
    CART_CHANGED = "CART_CHANGED"
    CART_UNAVAILABLE = "CART_UNAVAILABLE"
    EMPTY_CART = "EMPTY_CART"


class OrderConfirmed(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["confirmed"] = "confirmed"
    order: Order
    idempotent: bool = False


class StockUnavailable(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["stock_unavailable"] = "stock_unavailable"
    cart_id: UUID
    cart_version: int = Field(ge=0)
    shortages: tuple[StockShortage, ...] = Field(min_length=1)


class StaleCheckout(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["stale_checkout"] = "stale_checkout"
    cart_id: UUID | None
    reason: StaleCheckoutReason


ConfirmedOrderResult = Annotated[
    OrderConfirmed | StockUnavailable | StaleCheckout,
    Field(discriminator="kind"),
]


class StockRecoveryAction(str, Enum):
    ACCEPT_AVAILABLE = "ACCEPT_AVAILABLE"
    REMOVE_CART_ITEM = "REMOVE_CART_ITEM"
    VIEW_CART = "VIEW_CART"
    ABANDON_CHECKOUT = "ABANDON_CHECKOUT"


class StockRecoveryOption(BaseModel):
    model_config = ConfigDict(frozen=True)

    ordinal: int = Field(strict=True, ge=1)
    action: StockRecoveryAction
    shortage_ordinal: int | None = Field(default=None, strict=True, ge=1)
    cart_ordinal: int | None = Field(default=None, strict=True, ge=1)

    @model_validator(mode="after")
    def validate_target_namespace(self) -> StockRecoveryOption:
        if self.action == StockRecoveryAction.ACCEPT_AVAILABLE:
            if self.shortage_ordinal is None or self.cart_ordinal is not None:
                raise ValueError("Accept recovery requires only a shortage ordinal.")
        elif self.action == StockRecoveryAction.REMOVE_CART_ITEM:
            if self.shortage_ordinal is None or self.cart_ordinal is None:
                raise ValueError("Remove recovery requires shortage and cart ordinals.")
        elif self.shortage_ordinal is not None or self.cart_ordinal is not None:
            raise ValueError("Global recovery actions cannot have item ordinals.")
        return self


class StockRecoveryState(BaseModel):
    model_config = ConfigDict(frozen=True)

    cart_id: UUID
    cart_version: int = Field(ge=0)
    shortages: tuple[StockShortage, ...] = Field(min_length=1)
    options: tuple[StockRecoveryOption, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_option_ordinals(self) -> StockRecoveryState:
        if tuple(option.ordinal for option in self.options) != tuple(
            range(1, len(self.options) + 1)
        ):
            raise ValueError("Recovery option ordinals must be contiguous and ordered.")
        return self


class AvailableQuantityAccepted(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["accepted"] = "accepted"
    cart: Cart
    product_name: str
    unit: str
    quantity: Decimal = Field(gt=0, allow_inf_nan=False)


class RecoveryAvailabilityChanged(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["availability_changed"] = "availability_changed"
    shortage: StockShortage


AcceptAvailableQuantityResult = Annotated[
    AvailableQuantityAccepted | RecoveryAvailabilityChanged | StaleCheckout,
    Field(discriminator="kind"),
]

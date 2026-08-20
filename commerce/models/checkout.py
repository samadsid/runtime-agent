from __future__ import annotations

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .delivery_location import DeliveryLocationSnapshot
from .order import PaymentMethod
from .order_confirmation import StockRecoveryState


class CheckoutStage(str, Enum):
    NONE = "NONE"
    REVIEWING_CART = "REVIEWING_CART"
    COLLECTING_DETAILS = "COLLECTING_DETAILS"
    SELECTING_PAYMENT_METHOD = "SELECTING_PAYMENT_METHOD"
    READY_TO_CONFIRM = "READY_TO_CONFIRM"


class DeliveryDetailField(str, Enum):
    CUSTOMER_NAME = "customer_name"
    PHONE_NUMBER = "phone_number"
    DELIVERY_ADDRESS = "delivery_address"


class CheckoutState(BaseModel):
    model_config = ConfigDict(frozen=True)

    stage: CheckoutStage = CheckoutStage.NONE
    source_cart_id: UUID | None = None
    source_cart_version: int | None = Field(default=None, ge=0)
    customer_name: str | None = None
    phone_number: str | None = None
    delivery_address: str | None = None
    delivery_location: DeliveryLocationSnapshot | None = None
    pending_delivery_correction: DeliveryDetailField | None = None
    stock_recovery: StockRecoveryState | None = None
    payment_method: PaymentMethod | None = None

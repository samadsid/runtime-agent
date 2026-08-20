from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .delivery_location import DeliveryLocationSnapshot
from .fulfilment import FulfilmentActorType


class OrderStatus(str, Enum):
    AWAITING_PAYMENT = "AWAITING_PAYMENT"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    PAYMENT_EXPIRED = "PAYMENT_EXPIRED"
    CONFIRMED = "CONFIRMED"
    PREPARING = "PREPARING"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


class PaymentMethod(str, Enum):
    CASH_ON_DELIVERY = "CASH_ON_DELIVERY"
    ONLINE = "ONLINE"


class OrderItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    order_id: UUID
    product_id: UUID
    product_name: str
    unit: str
    unit_price: Decimal = Field(allow_inf_nan=False)
    currency: str = "INR"
    quantity: Decimal = Field(gt=0, allow_inf_nan=False)


class OrderStatusHistory(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    order_id: UUID
    from_status: OrderStatus | None
    to_status: OrderStatus
    actor_id: UUID | None
    actor_type: FulfilmentActorType
    reason: str | None
    created_at: datetime


class Order(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    tenant_id: UUID
    public_order_number: str = Field(min_length=1, max_length=32)
    source_cart_id: UUID
    conversation_id: UUID
    status: OrderStatus
    payment_method: PaymentMethod
    customer_name: str
    phone_number: str
    delivery_address: str
    delivery_location: DeliveryLocationSnapshot | None = None
    created_at: datetime
    confirmed_at: datetime | None
    version: int = Field(default=1, ge=1)
    updated_at: datetime | None = None
    items: tuple[OrderItem, ...] = ()
    status_history: tuple[OrderStatusHistory, ...] = ()

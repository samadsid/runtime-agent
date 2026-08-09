from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .fulfilment import FulfilmentActorType


class OrderStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    PREPARING = "PREPARING"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


class PaymentMethod(str, Enum):
    CASH_ON_DELIVERY = "CASH_ON_DELIVERY"


class OrderItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    order_id: UUID
    product_id: UUID
    product_name: str
    unit: str
    unit_price: Decimal = Field(allow_inf_nan=False)
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
    source_cart_id: UUID
    conversation_id: UUID
    status: OrderStatus
    payment_method: PaymentMethod
    customer_name: str
    phone_number: str
    delivery_address: str
    created_at: datetime
    confirmed_at: datetime
    items: tuple[OrderItem, ...] = ()
    status_history: tuple[OrderStatusHistory, ...] = ()

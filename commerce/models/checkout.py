from __future__ import annotations

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CheckoutStage(str, Enum):
    NONE = "NONE"
    REVIEWING_CART = "REVIEWING_CART"
    COLLECTING_DETAILS = "COLLECTING_DETAILS"
    READY_TO_CONFIRM = "READY_TO_CONFIRM"


class CheckoutState(BaseModel):
    model_config = ConfigDict(frozen=True)

    stage: CheckoutStage = CheckoutStage.NONE
    source_cart_id: UUID | None = None
    customer_name: str | None = None
    phone_number: str | None = None
    delivery_address: str | None = None

from __future__ import annotations

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .cart_item import CartItem


class CartStatus(str, Enum):
    ACTIVE = "ACTIVE"
    CHECKED_OUT = "CHECKED_OUT"


class Cart(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    tenant_id: UUID
    conversation_id: UUID
    status: CartStatus
    version: int = Field(default=0, ge=0)
    items: tuple[CartItem, ...] = ()

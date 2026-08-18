from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DeferredCustomerIntentKind(str, Enum):
    BROWSE_CATALOG = "BROWSE_CATALOG"
    SEARCH_PRODUCT = "SEARCH_PRODUCT"
    DIRECT_CART_ADD = "DIRECT_CART_ADD"
    VIEW_CART = "VIEW_CART"
    ORDER_MANAGEMENT = "ORDER_MANAGEMENT"


class DeferredOrderAction(str, Enum):
    GET_STATUS = "GET_STATUS"
    LIST = "LIST"
    VIEW_DETAILS = "VIEW_DETAILS"
    CANCEL = "CANCEL"


class DeferredCustomerIntent(BaseModel):
    """Bounded, validated projection of an intent blocked by onboarding."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: DeferredCustomerIntentKind
    category_query: str | None = Field(default=None, min_length=1, max_length=100)
    product_query: str | None = Field(default=None, min_length=1, max_length=200)
    quantity: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    stated_unit: str | None = Field(default=None, min_length=1, max_length=32)
    order_action: DeferredOrderAction | None = None
    order_reference: str | None = Field(default=None, min_length=1, max_length=100)
    order_ordinal: int | None = Field(default=None, ge=1)
    order_latest: bool = False
    order_limit: int | None = Field(default=None, ge=1, le=10)
    order_confirmed: bool = False
    source_request_id: str = Field(min_length=1, max_length=320)
    created_at: datetime

    @model_validator(mode="after")
    def validate_kind_contract(self) -> DeferredCustomerIntent:
        if (
            self.kind is DeferredCustomerIntentKind.SEARCH_PRODUCT
            and not self.product_query
        ):
            raise ValueError("Deferred search requires a product query.")
        if self.kind is DeferredCustomerIntentKind.DIRECT_CART_ADD and (
            not self.product_query or self.quantity is None
        ):
            raise ValueError("Deferred direct add requires product and quantity.")
        if (
            self.kind is DeferredCustomerIntentKind.ORDER_MANAGEMENT
            and self.order_action is None
        ):
            raise ValueError("Deferred order management requires an action.")
        if (
            self.kind is not DeferredCustomerIntentKind.ORDER_MANAGEMENT
            and self.order_action is not None
        ):
            raise ValueError("Order action is restricted to deferred order management.")
        return self

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .cart_editing import PendingCartClear
from .cart_item import CartItem
from .checkout import CheckoutState
from .customer_order import OrderSummary, PendingOrderCancellation
from .direct_cart import PendingCartAddition
from .product import Product
from .saved_delivery import (
    CustomerOnboardingState,
    PendingSavedDetailsSave,
    PendingSavedProfileUse,
    SavedAddressOption,
)


class CommerceSession(BaseModel):
    model_config = ConfigDict(frozen=True)

    recent_product_results: tuple[Product, ...] = ()
    selected_product: Product | None = None
    cart_items: tuple[CartItem, ...] = ()
    pending_cart_clear: PendingCartClear | None = None
    pending_cart_addition: PendingCartAddition | None = None
    checkout: CheckoutState = Field(default_factory=CheckoutState)
    recent_order_results: tuple[OrderSummary, ...] = ()
    pending_order_cancellation: PendingOrderCancellation | None = None
    recent_saved_addresses: tuple[SavedAddressOption, ...] = ()
    pending_saved_profile_use: PendingSavedProfileUse | None = None
    pending_saved_details_save: PendingSavedDetailsSave | None = None
    customer_onboarding: CustomerOnboardingState = Field(
        default_factory=CustomerOnboardingState
    )

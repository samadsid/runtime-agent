from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .cart_item import CartItem
from .product import Product


class CommerceSession(BaseModel):
    model_config = ConfigDict(frozen=True)

    recent_product_results: tuple[Product, ...] = ()
    selected_product: Product | None = None
    cart_items: tuple[CartItem, ...] = ()

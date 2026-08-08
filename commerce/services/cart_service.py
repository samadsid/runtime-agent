from __future__ import annotations

from decimal import Decimal

from commerce.models import CartItem, CommerceSession, Product


class CartService:
    def add_or_replace(
        self,
        session: CommerceSession,
        product: Product,
        quantity: Decimal,
    ) -> CommerceSession:
        item = CartItem(product=product, quantity=quantity)
        cart_items = list(session.cart_items)

        for index, existing in enumerate(cart_items):
            if existing.product.id == product.id:
                cart_items[index] = item
                break
        else:
            cart_items.append(item)

        return session.model_copy(update={"cart_items": tuple(cart_items)})

    def remove(
        self,
        session: CommerceSession,
        index: int,
    ) -> CommerceSession:
        cart_items = (
            session.cart_items[:index]
            + session.cart_items[index + 1 :]
        )
        return session.model_copy(update={"cart_items": cart_items})

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from commerce.models import (
    Cart,
    CartItem,
    CartStatus,
    Order,
    OrderItem,
    OrderStatus,
    PaymentMethod,
    Product,
)
from commerce.repositories import (
    CartNotAvailableForCheckoutError,
    CartRepository,
    InvalidCartOrdinalError,
    OrderRepository,
)


class InMemoryCartRepository(CartRepository):
    def __init__(
        self,
        products: tuple[Product, ...] = (),
        items: tuple[CartItem, ...] = (),
    ) -> None:
        self.products = {product.id: product for product in products}
        self.products.update({item.product.id: item.product for item in items})
        self.carts: dict[tuple[UUID, UUID], Cart] = {}
        if items:
            self.carts[(UUID(int=0), UUID(int=0))] = Cart(
                id=uuid4(),
                tenant_id=UUID(int=0),
                conversation_id=UUID(int=0),
                status=CartStatus.ACTIVE,
                items=items,
            )
        self.fail_writes = False

    async def get_or_create_active_cart(
        self, tenant_id: UUID, conversation_id: UUID
    ) -> Cart:
        key = (tenant_id, conversation_id)
        if key not in self.carts or self.carts[key].status != CartStatus.ACTIVE:
            self.carts[key] = Cart(
                id=uuid4(),
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                status=CartStatus.ACTIVE,
            )
        return self.carts[key]

    async def add_or_replace_item(
        self, cart_id: UUID, product_id: UUID, quantity: Decimal
    ) -> Cart:
        cart = next(cart for cart in self.carts.values() if cart.id == cart_id)
        return self._replace(cart, product_id, quantity)

    async def get_or_create_active_cart_and_add_or_replace_item(
        self,
        tenant_id: UUID,
        conversation_id: UUID,
        product_id: UUID,
        quantity: Decimal,
    ) -> Cart:
        if self.fail_writes:
            raise RuntimeError("persistence failed")
        cart = await self.get_or_create_active_cart(tenant_id, conversation_id)
        return self._replace(cart, product_id, quantity)

    async def get_active_cart(
        self, tenant_id: UUID, conversation_id: UUID
    ) -> Cart | None:
        cart = self.carts.get((tenant_id, conversation_id))
        if cart is None or cart.status != CartStatus.ACTIVE:
            return None
        return cart

    async def remove_item_by_ordinal(self, cart_id: UUID, ordinal: int) -> Cart:
        cart = next(cart for cart in self.carts.values() if cart.id == cart_id)
        index = ordinal - 1
        if index < 0 or index >= len(cart.items):
            raise InvalidCartOrdinalError
        updated = cart.model_copy(
            update={"items": cart.items[:index] + cart.items[index + 1 :]}
        )
        self.carts[(cart.tenant_id, cart.conversation_id)] = updated
        return updated

    def _replace(self, cart: Cart, product_id: UUID, quantity: Decimal) -> Cart:
        product = self.products[product_id]
        item = CartItem(product=product, quantity=quantity)
        items = list(cart.items)
        for index, existing in enumerate(items):
            if existing.product.id == product_id:
                items[index] = item
                break
        else:
            items.append(item)
        updated = cart.model_copy(update={"items": tuple(items)})
        self.carts[(cart.tenant_id, cart.conversation_id)] = updated
        return updated


class InMemoryOrderRepository(OrderRepository):
    def __init__(self, cart_repository: InMemoryCartRepository) -> None:
        self.cart_repository = cart_repository
        self.orders: list[Order] = []
        self.fail_creation = False

    async def create_confirmed_order_from_cart(
        self,
        conversation_id: UUID,
        cart_id: UUID,
        customer_name: str,
        phone_number: str,
        delivery_address: str,
    ) -> Order:
        existing = next(
            (order for order in self.orders if order.source_cart_id == cart_id), None
        )
        if existing is not None:
            return existing
        if self.fail_creation:
            raise RuntimeError("order persistence failed")
        cart = next(
            (cart for cart in self.cart_repository.carts.values() if cart.id == cart_id),
            None,
        )
        if (
            cart is None
            or cart.conversation_id != conversation_id
            or cart.status != CartStatus.ACTIVE
            or not cart.items
        ):
            raise CartNotAvailableForCheckoutError

        order_id = uuid4()
        now = datetime.now(timezone.utc)
        order = Order(
            id=order_id,
            source_cart_id=cart_id,
            conversation_id=conversation_id,
            status=OrderStatus.CONFIRMED,
            payment_method=PaymentMethod.CASH_ON_DELIVERY,
            customer_name=customer_name,
            phone_number=phone_number,
            delivery_address=delivery_address,
            created_at=now,
            confirmed_at=now,
            items=tuple(
                OrderItem(
                    id=uuid4(),
                    order_id=order_id,
                    product_id=item.product.id,
                    product_name=item.product.name,
                    unit=item.product.unit,
                    unit_price=item.product.price,
                    quantity=item.quantity,
                )
                for item in cart.items
            ),
        )
        self.orders.append(order)
        closed = cart.model_copy(update={"status": CartStatus.CHECKED_OUT})
        self.cart_repository.carts[(cart.tenant_id, cart.conversation_id)] = closed
        return order

    async def get_latest_order(self, conversation_id: UUID) -> Order | None:
        matches = [
            order for order in self.orders if order.conversation_id == conversation_id
        ]
        return matches[-1] if matches else None

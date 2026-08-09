from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from commerce.models import (
    Cart,
    CartItem,
    CartStatus,
    FulfilmentActor,
    Order,
    OrderItem,
    OrderStatus,
    OrderStatusHistory,
    OrderSummary,
    PaymentMethod,
    Product,
)
from commerce.repositories import (
    CartItemOrdinalError,
    CartNotAvailableForCheckoutError,
    CartNotFoundError,
    CartRepository,
    InvalidCartOrdinalError,
    OrderRepository,
    StaleCartError,
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
            update={
                "items": cart.items[:index] + cart.items[index + 1 :],
                "version": cart.version + 1,
            }
        )
        self.carts[(cart.tenant_id, cart.conversation_id)] = updated
        return updated

    async def update_item_quantity_by_ordinal(
        self,
        tenant_id: UUID,
        conversation_id: UUID,
        ordinal: int,
        quantity: Decimal,
    ) -> Cart:
        if self.fail_writes:
            raise RuntimeError("persistence failed")
        cart = await self.get_active_cart(tenant_id, conversation_id)
        if cart is None:
            raise CartNotFoundError
        index = ordinal - 1
        if index < 0 or index >= len(cart.items):
            raise CartItemOrdinalError
        if cart.items[index].quantity == quantity:
            return cart
        items = list(cart.items)
        items[index] = items[index].model_copy(update={"quantity": quantity})
        updated = cart.model_copy(
            update={"items": tuple(items), "version": cart.version + 1}
        )
        self.carts[(tenant_id, conversation_id)] = updated
        return updated

    async def clear_active_cart(
        self,
        tenant_id: UUID,
        conversation_id: UUID,
        cart_id: UUID,
        expected_version: int,
    ) -> Cart:
        if self.fail_writes:
            raise RuntimeError("persistence failed")
        cart = await self.get_active_cart(tenant_id, conversation_id)
        if cart is None or cart.id != cart_id:
            raise CartNotFoundError
        if cart.version != expected_version:
            raise StaleCartError
        updated = cart.model_copy(
            update={"items": (), "version": cart.version + 1}
        )
        self.carts[(tenant_id, conversation_id)] = updated
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
        updated = cart.model_copy(
            update={
                "items": tuple(items),
                "version": cart.version + 1,
            }
        )
        self.carts[(cart.tenant_id, cart.conversation_id)] = updated
        return updated


class InMemoryOrderRepository(OrderRepository):
    def __init__(self, cart_repository: InMemoryCartRepository) -> None:
        self.cart_repository = cart_repository
        self.orders: list[Order] = []
        self.history: list[OrderStatusHistory] = []
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
            (
                cart
                for cart in self.cart_repository.carts.values()
                if cart.id == cart_id
            ),
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

    async def list_for_conversation(
        self, conversation_id: UUID, limit: int
    ) -> tuple[OrderSummary, ...]:
        matches = sorted(
            (
                order
                for order in self.orders
                if order.conversation_id == conversation_id
            ),
            key=lambda order: (order.created_at, order.id),
            reverse=True,
        )[:limit]
        return tuple(
            OrderSummary(
                order_id=order.id,
                status=order.status,
                created_at=order.created_at,
                item_count=len(order.items),
                total_amount=sum(
                    (item.unit_price * item.quantity for item in order.items),
                    Decimal(0),
                ),
            )
            for order in matches
        )

    async def get_for_conversation(
        self,
        conversation_id: UUID,
        order_id: UUID,
        *,
        for_update: bool = False,
    ) -> Order | None:
        order = next(
            (
                candidate
                for candidate in self.orders
                if candidate.id == order_id
                and candidate.conversation_id == conversation_id
            ),
            None,
        )
        if order is None:
            return None
        return order.model_copy(
            update={"status_history": await self.get_status_history(order.id)}
        )

    async def get_latest_for_conversation(
        self, conversation_id: UUID
    ) -> Order | None:
        matches = [
            order for order in self.orders if order.conversation_id == conversation_id
        ]
        if not matches:
            return None
        latest = max(matches, key=lambda order: (order.created_at, order.id))
        return await self.get_for_conversation(conversation_id, latest.id)

    async def get_latest_order(self, conversation_id: UUID) -> Order | None:
        return await self.get_latest_for_conversation(conversation_id)

    async def get_by_id(
        self, order_id: UUID, *, for_update: bool = False
    ) -> Order | None:
        return next((order for order in self.orders if order.id == order_id), None)

    async def transition_status(
        self,
        order_id: UUID,
        target_status: OrderStatus,
        actor: FulfilmentActor,
        reason: str | None = None,
    ) -> Order:
        order = await self.get_by_id(order_id)
        if order is None:
            raise LookupError(order_id)
        if order.status == target_status:
            return order
        index = self.orders.index(order)
        self.history.append(
            OrderStatusHistory(
                id=uuid4(),
                order_id=order_id,
                from_status=order.status,
                to_status=target_status,
                actor_id=actor.actor_id,
                actor_type=actor.actor_type,
                reason=reason,
                created_at=datetime.now(timezone.utc),
            )
        )
        transitioned = order.model_copy(
            update={"status": target_status}
        ).model_copy(
            update={"status_history": await self.get_status_history(order_id)}
        )
        self.orders[index] = transitioned
        return transitioned

    async def get_status_history(
        self, order_id: UUID
    ) -> tuple[OrderStatusHistory, ...]:
        return tuple(
            row for row in getattr(self, "history", []) if row.order_id == order_id
        )

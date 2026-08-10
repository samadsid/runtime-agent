from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from commerce.models import (
    CartItem,
    CheckoutStage,
    CheckoutState,
    CommerceSession,
    DeliveryDetailField,
    OrderStatus,
    OrderSummary,
    PendingCartClear,
    PendingOrderCancellation,
    Product,
)
from runtime.graph.memory import GraphCheckpointer


def test_configured_serializer_round_trips_durable_commerce_models(
    caplog,
) -> None:
    product = Product(
        id=uuid4(),
        name="Chicken Breast",
        price=Decimal("320.00"),
        unit="kg",
    )
    session = CommerceSession(
        recent_product_results=(product,),
        selected_product=product,
        cart_items=(CartItem(product=product, quantity=Decimal(2)),),
        pending_cart_clear=PendingCartClear(
            cart_id=(cart_id := uuid4()),
            cart_version=4,
            requested_at=datetime.now(timezone.utc),
        ),
        checkout=CheckoutState(
            stage=CheckoutStage.COLLECTING_DETAILS,
            source_cart_id=uuid4(),
            customer_name="Samad",
            pending_delivery_correction=DeliveryDetailField.DELIVERY_ADDRESS,
        ),
        recent_order_results=(
            OrderSummary(
                order_id=(order_id := uuid4()),
                status=OrderStatus.CONFIRMED,
                created_at=datetime.now(timezone.utc),
                item_count=1,
                total_amount=Decimal("640.00"),
            ),
        ),
        pending_order_cancellation=PendingOrderCancellation(
            order_id=order_id,
            requested_at=datetime.now(timezone.utc),
        ),
    )
    serializer = GraphCheckpointer().instance.serde

    encoded = serializer.dumps_typed(session)
    restored = serializer.loads_typed(encoded)

    assert restored == session
    assert restored.cart_items[0].quantity == Decimal(2)
    assert restored.pending_cart_clear == session.pending_cart_clear
    assert restored.pending_cart_clear.cart_id == cart_id
    assert restored.checkout == session.checkout
    assert (
        restored.checkout.pending_delivery_correction
        == DeliveryDetailField.DELIVERY_ADDRESS
    )
    assert restored.recent_order_results == session.recent_order_results
    assert restored.pending_order_cancellation == session.pending_order_cancellation
    assert "Deserializing unregistered type" not in caplog.text

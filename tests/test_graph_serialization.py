from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from asyncpg.pgproto.pgproto import UUID as AsyncpgUUID

from commerce.models import (
    CartItem,
    CheckoutStage,
    CheckoutState,
    CommerceSession,
    DeliveryDetailField,
    OrderStatus,
    OrderSummary,
    PaymentMethod,
    PendingCartAddition,
    PendingCartClear,
    PendingCartProductOption,
    PendingOrderCancellation,
    Product,
    StockRecoveryAction,
    StockRecoveryOption,
    StockRecoveryState,
    StockShortage,
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
        pending_cart_addition=PendingCartAddition(
            options=(
                PendingCartProductOption(
                    product_id=product.id,
                    display_name=product.name,
                    canonical_unit=product.unit,
                ),
            ),
            quantity=Decimal(3),
            stated_unit="kg",
            created_at=datetime.now(timezone.utc),
            source_request_id="request-1",
        ),
        checkout=CheckoutState(
            stage=CheckoutStage.COLLECTING_DETAILS,
            source_cart_id=(checkout_cart_id := AsyncpgUUID(str(uuid4()))),
            source_cart_version=7,
            customer_name="Samad",
            pending_delivery_correction=DeliveryDetailField.DELIVERY_ADDRESS,
            payment_method=PaymentMethod.ONLINE,
            stock_recovery=StockRecoveryState(
                cart_id=checkout_cart_id,
                cart_version=7,
                shortages=(
                    StockShortage(
                        product_id=product.id,
                        product_name=product.name,
                        unit=product.unit,
                        requested_quantity=Decimal(2),
                        available_quantity=Decimal(1),
                    ),
                ),
                options=(
                    StockRecoveryOption(
                        ordinal=1,
                        action=StockRecoveryAction.ACCEPT_AVAILABLE,
                        shortage_ordinal=1,
                    ),
                ),
            ),
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
    assert restored.pending_cart_addition == session.pending_cart_addition
    assert restored.checkout == session.checkout
    assert restored.checkout.stage is CheckoutStage.COLLECTING_DETAILS
    assert restored.checkout.payment_method is PaymentMethod.ONLINE
    assert isinstance(restored.checkout.source_cart_id, AsyncpgUUID)
    assert restored.checkout.stock_recovery == session.checkout.stock_recovery
    assert (
        restored.checkout.pending_delivery_correction
        == DeliveryDetailField.DELIVERY_ADDRESS
    )
    assert restored.recent_order_results == session.recent_order_results
    assert restored.pending_order_cancellation == session.pending_order_cancellation
    assert "Deserializing unregistered type" not in caplog.text

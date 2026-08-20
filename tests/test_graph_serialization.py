from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from asyncpg.pgproto.pgproto import UUID as AsyncpgUUID

from commerce.models import (
    CartItem,
    CartStatus,
    CatalogBrowseKind,
    CatalogBrowseState,
    CatalogProductOption,
    CheckoutStage,
    CheckoutState,
    CommerceSession,
    CustomerLocationUse,
    CustomerOnboardingState,
    DeferredCustomerIntent,
    DeferredCustomerIntentKind,
    DeliveryDetailField,
    DeliveryInputMode,
    DeliveryLocationSnapshot,
    OnboardingStage,
    OrderStatus,
    OrderSummary,
    PaymentMethod,
    PendingCartAddition,
    PendingCartClear,
    PendingCartProductOption,
    PendingCustomerLocation,
    PendingDeliveryLocation,
    PendingOrderCancellation,
    Product,
    ProductStatus,
    StockRecoveryAction,
    StockRecoveryOption,
    StockRecoveryState,
    StockShortage,
)
from runtime.graph.memory import GraphCheckpointer


def test_configured_serializer_allows_direct_order_status_enum() -> None:
    serializer = GraphCheckpointer().instance.serde

    restored = serializer.loads_typed(serializer.dumps_typed(OrderStatus.CONFIRMED))

    assert restored is OrderStatus.CONFIRMED


def test_legacy_onboarding_checkpoint_values_normalize_to_canonical_state() -> None:
    restored = CustomerOnboardingState.model_validate(
        {
            "stage": "REVIEWING_DETAILS",
            "pending_customer_name": "Samad",
            "pending_phone_number": "9999999999",
            "pending_delivery_address": "B-68, Delhi",
        }
    )

    assert restored.stage is OnboardingStage.REVIEWING_PROFILE
    assert restored.pending_address_details == "B-68, Delhi"


@pytest.mark.parametrize(
    "value",
    (ProductStatus.ACTIVE, CartStatus.ACTIVE, DeliveryDetailField.DELIVERY_ADDRESS),
)
def test_configured_serializer_allows_nested_durable_enums(value: object) -> None:
    serializer = GraphCheckpointer().instance.serde

    restored = serializer.loads_typed(serializer.dumps_typed(value))

    assert restored is value


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
        customer_onboarding=CustomerOnboardingState(
            stage=OnboardingStage.COLLECTING_LOCATION,
            delivery_input_mode=DeliveryInputMode.WHATSAPP_LOCATION,
            pending_customer_name="Samad",
            pending_phone_number="9999999999",
        ),
        pending_customer_location=PendingCustomerLocation(
            delivery_location=PendingDeliveryLocation(
                latitude=Decimal("28.612345"),
                longitude=Decimal("77.234567"),
                zone_id=uuid4(),
                zone_name="Delhi East",
                zone_version=2,
                formatted_area="New Zafrabad, Delhi",
                checked_at=datetime.now(timezone.utc),
                source_inbound_message_id=uuid4(),
            ),
            use=CustomerLocationUse.TEMPORARY,
            address_details="B-68, 2nd Floor",
        ),
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
        catalog_browse=CatalogBrowseState(
            kind=CatalogBrowseKind.PRODUCTS,
            products=(
                CatalogProductOption(
                    product_id=product.id,
                    name=product.name,
                    price=product.price,
                    currency=product.currency,
                    unit=product.unit,
                    available=True,
                ),
            ),
            page=1,
            has_previous=False,
            has_next=True,
            created_at=datetime.now(timezone.utc),
        ),
        checkout=CheckoutState(
            stage=CheckoutStage.COLLECTING_DETAILS,
            source_cart_id=(checkout_cart_id := AsyncpgUUID(str(uuid4()))),
            source_cart_version=7,
            customer_name="Samad",
            pending_delivery_correction=DeliveryDetailField.DELIVERY_ADDRESS,
            payment_method=PaymentMethod.ONLINE,
            delivery_location=DeliveryLocationSnapshot(
                latitude=Decimal("28.612345"),
                longitude=Decimal("77.234567"),
                zone_id=uuid4(),
                zone_name="Delhi East",
                zone_version=2,
                formatted_area="New Zafrabad, Delhi",
                address_details="B-68, 2nd Floor",
                checked_at=datetime.now(timezone.utc),
            ),
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
                    public_order_number="MU-260818-0001",
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
        deferred_customer_intent=DeferredCustomerIntent(
            kind=DeferredCustomerIntentKind.DIRECT_CART_ADD,
            product_query="Chicken Breast",
            quantity=Decimal(2),
            stated_unit="kg",
            source_request_id="whatsapp:wamid.original",
            created_at=datetime.now(timezone.utc),
        ),
    )
    serializer = GraphCheckpointer().instance.serde

    encoded = serializer.dumps_typed(session)
    restored = serializer.loads_typed(encoded)

    assert restored == session
    assert restored.customer_onboarding.stage is OnboardingStage.COLLECTING_LOCATION
    assert (
        restored.customer_onboarding.delivery_input_mode
        is DeliveryInputMode.WHATSAPP_LOCATION
    )
    assert restored.pending_customer_location == session.pending_customer_location
    assert restored.cart_items[0].quantity == Decimal(2)
    assert restored.pending_cart_clear == session.pending_cart_clear
    assert restored.pending_cart_clear.cart_id == cart_id
    assert restored.pending_cart_addition == session.pending_cart_addition
    assert restored.catalog_browse == session.catalog_browse
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
    assert restored.deferred_customer_intent == session.deferred_customer_intent
    assert "Deserializing unregistered type" not in caplog.text

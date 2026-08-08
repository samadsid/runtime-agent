from decimal import Decimal
from uuid import uuid4

from commerce.models import CartItem, CommerceSession, Product
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
    )
    serializer = GraphCheckpointer().instance.serde

    encoded = serializer.dumps_typed(session)
    restored = serializer.loads_typed(encoded)

    assert restored == session
    assert restored.cart_items[0].quantity == Decimal(2)
    assert "Deserializing unregistered type" not in caplog.text

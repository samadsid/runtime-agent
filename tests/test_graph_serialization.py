from decimal import Decimal
from uuid import uuid4

from commerce.models import CommerceSession, Product
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
    )
    serializer = GraphCheckpointer().instance.serde

    encoded = serializer.dumps_typed(session)
    restored = serializer.loads_typed(encoded)

    assert restored == session
    assert "Deserializing unregistered type" not in caplog.text

from decimal import Decimal
from uuid import uuid4

from commerce.models import CommerceSession, Product
from runtime.prompts.renderers import CommerceSessionRenderer


def test_commerce_session_renderer_preserves_result_ordinals() -> None:
    first = Product(
        id=uuid4(),
        name="Chicken Breast",
        price=Decimal("320.00"),
        unit="kg",
    )
    second = Product(
        id=uuid4(),
        name="Chicken Wings",
        price=Decimal("220.00"),
        unit="kg",
    )
    session = CommerceSession(
        recent_product_results=(first, second),
        selected_product=first,
    )

    rendered = CommerceSessionRenderer().render(session)

    assert rendered == (
        "Recent product results:\n"
        "1. Chicken Breast\n"
        "2. Chicken Wings\n"
        "Selected product:\n"
        "Chicken Breast"
    )

from decimal import Decimal
from uuid import uuid4

from commerce.models import CartItem, CommerceSession, Product
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
        "Chicken Breast\n"
        "Cart items:\n"
        "None.\n"
        "Pending cart clear:\n"
        "None.\n"
        "Checkout state:\n"
        "Stage: NONE\n"
        "Source cart: missing\n"
        "Customer name: missing\n"
        "Phone number: missing\n"
        "Delivery address: missing\n"
        "Pending delivery correction:\n"
        "None.\n"
        "Recent order results:\n"
        "None.\n"
        "Pending order cancellation:\n"
        "None."
    )


def test_commerce_session_renderer_separates_cart_ordinals() -> None:
    search_result = Product(
        id=uuid4(),
        name="Search Result",
        price=Decimal("100.00"),
        unit="kg",
    )
    cart_product = Product(
        id=uuid4(),
        name="Cart Product",
        price=Decimal("200.00"),
        unit="pack",
    )
    session = CommerceSession(
        recent_product_results=(search_result,),
        selected_product=search_result,
        cart_items=(CartItem(product=cart_product, quantity=Decimal("2.5")),),
    )

    rendered = CommerceSessionRenderer().render(session)

    assert "Recent product results:\n1. Search Result" in rendered
    assert "Cart items:\n1. Cart Product — 2.5 pack" in rendered

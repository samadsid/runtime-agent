from decimal import Decimal
from uuid import uuid4

import pytest

from commerce.models import CommerceSession, Product
from runtime.capabilities import CapabilityInput
from runtime.capabilities.search_product import SearchProductCapability
from runtime.capabilities.select_product import SelectProductCapability


class StubSearchService:
    def __init__(self, products: list[Product]) -> None:
        self.products = products

    async def search(self, query: str) -> list[Product]:
        return self.products


def product(name: str) -> Product:
    return Product(
        id=uuid4(),
        name=name,
        price=Decimal("10.00"),
        unit="kg",
    )


@pytest.mark.asyncio
async def test_search_retains_ordered_results_and_clears_selection() -> None:
    breast = product("Chicken Breast")
    wings = product("Chicken Wings")
    old = product("Old Product")
    session = CommerceSession(
        recent_product_results=(old,),
        selected_product=old,
    )
    capability = SearchProductCapability(
        service=StubSearchService([breast, wings]),  # type: ignore[arg-type]
    )

    output = await capability.execute(
        CapabilityInput[CommerceSession](
            data={"query": "chicken"},
            session=session,
        )
    )

    assert output.session.recent_product_results == (breast, wings)
    assert output.session.selected_product is None
    assert output.message == (
        "Available products:\n\nChicken Breast - ₹10.00/kg\nChicken Wings - ₹10.00/kg"
    )


@pytest.mark.asyncio
async def test_zero_result_search_clears_stale_product_context() -> None:
    old = product("Old Product")
    session = CommerceSession(
        recent_product_results=(old,),
        selected_product=old,
    )
    capability = SearchProductCapability(
        service=StubSearchService([]),  # type: ignore[arg-type]
    )

    output = await capability.execute(
        CapabilityInput[CommerceSession](
            data={"query": "missing"},
            session=session,
        )
    )

    assert output.session == CommerceSession()
    assert output.message == "No products found for 'missing'."


@pytest.mark.asyncio
async def test_missing_search_query_preserves_session() -> None:
    existing = product("Existing")
    session = CommerceSession(recent_product_results=(existing,))
    capability = SearchProductCapability(
        service=StubSearchService([]),  # type: ignore[arg-type]
    )

    output = await capability.execute(
        CapabilityInput[CommerceSession](data={}, session=session)
    )

    assert output.session is session
    assert output.success is False


@pytest.mark.asyncio
async def test_first_ordinal_selects_exact_first_retained_product() -> None:
    breast = product("Chicken Breast")
    wings = product("Chicken Wings")
    session = CommerceSession(recent_product_results=(breast, wings))

    output = await SelectProductCapability().execute(
        CapabilityInput[CommerceSession](
            data={"ordinal": 1},
            session=session,
        )
    )

    assert output.success is True
    assert output.session.recent_product_results == (breast, wings)
    assert output.session.selected_product is breast
    assert output.message == "Selected Chicken Breast."


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"ordinal": 0},
        {"ordinal": -1},
        {"ordinal": 3},
        {"ordinal": "1"},
        {"ordinal": True},
    ],
)
async def test_invalid_ordinal_never_changes_selection(
    arguments: dict[str, object],
) -> None:
    breast = product("Chicken Breast")
    session = CommerceSession(recent_product_results=(breast,))

    output = await SelectProductCapability().execute(
        CapabilityInput[CommerceSession](
            data=arguments,
            session=session,
        )
    )

    assert output.success is False
    assert output.session is session
    assert output.session.selected_product is None

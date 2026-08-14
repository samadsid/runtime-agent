from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from commerce.models import (
    CatalogBrowseKind,
    Category,
    CommerceSession,
    Product,
)
from commerce.repositories import InMemoryProductRepository
from commerce.services import (
    CatalogBrowsePolicy,
    CatalogBrowseResultKind,
    CatalogBrowseService,
)
from runtime.capabilities import CapabilityInput, ExecutionContext
from runtime.capabilities.browse_catalog import BrowseCatalogCapability
from runtime.capabilities.resolve_catalog_browse import (
    ResolveCatalogBrowseArguments,
    ResolveCatalogBrowseCapability,
)
from runtime.contracts import ExecutionStatus, GeneratedExecutionOutcome

TENANT = UUID("10000000-0000-0000-0000-000000000001")


def product(name: str, available: bool = True) -> Product:
    return Product(
        id=uuid4(),
        name=name,
        price=Decimal("10.50"),
        currency="INR",
        unit="kg",
        available=available,
    )


def input_for(session: CommerceSession, data: dict) -> CapabilityInput[CommerceSession]:
    return CapabilityInput(
        data=data,
        session=session,
        context=ExecutionContext(tenant_id=TENANT, conversation_id=uuid4()),
    )


@pytest.mark.asyncio
async def test_small_catalog_auto_returns_bounded_products() -> None:
    products = [product("Wings"), product("Breast")]
    repository = InMemoryProductRepository(products)
    service = CatalogBrowseService(
        repository,
        CatalogBrowsePolicy(product_page_size=1, direct_product_limit=10),
    )

    result = await service.browse(TENANT)

    assert result.kind is CatalogBrowseResultKind.PRODUCTS
    assert result.products is not None
    assert [item.name for item in result.products.items] == ["Breast"]
    assert result.products.has_next is True


@pytest.mark.asyncio
async def test_large_catalog_returns_categories_and_category_products() -> None:
    chicken = Category(id=uuid4(), tenant_id=TENANT, name="Chicken")
    seafood = Category(id=uuid4(), tenant_id=TENANT, name="Seafood")
    breast = product("Chicken Breast")
    fish = product("Fish")
    repository = InMemoryProductRepository(
        [breast, fish],
        [chicken, seafood],
        {breast.id: chicken.id, fish.id: seafood.id},
    )
    service = CatalogBrowseService(
        repository, CatalogBrowsePolicy(direct_product_limit=1)
    )

    initial = await service.browse(TENANT)
    category = await service.browse(TENANT, category_query="chicken")

    assert initial.kind is CatalogBrowseResultKind.CATEGORIES
    assert initial.categories is not None
    assert [item.name for item in initial.categories.items] == ["Chicken", "Seafood"]
    assert category.products is not None
    assert [item.name for item in category.products.items] == ["Chicken Breast"]


@pytest.mark.asyncio
async def test_browse_capability_stores_page_and_resolver_selects_reloaded_product() -> (
    None
):
    now = datetime.now(timezone.utc)
    breast = product("Chicken Breast")
    repository = InMemoryProductRepository([breast])
    service = CatalogBrowseService(repository, CatalogBrowsePolicy())
    browse = BrowseCatalogCapability(service, clock=lambda: now)
    shown = await browse.execute(input_for(CommerceSession(), {}))

    assert shown.session.catalog_browse is not None
    assert shown.session.catalog_browse.kind is CatalogBrowseKind.PRODUCTS
    assert isinstance(shown.outcome, GeneratedExecutionOutcome)
    assert shown.outcome.fragments[0].id == "catalog-product-1"

    resolved = await ResolveCatalogBrowseCapability(service, clock=lambda: now).execute(
        input_for(shown.session, {"ordinal": 1})
    )

    assert resolved.session.catalog_browse is None
    assert resolved.session.selected_product == breast
    assert resolved.session.recent_product_results == (breast,)
    assert resolved.outcome.status is ExecutionStatus.SUCCESS


@pytest.mark.asyncio
async def test_invalid_navigation_preserves_state_and_expiry_clears_only_browse() -> (
    None
):
    now = datetime.now(timezone.utc)
    repository = InMemoryProductRepository([product("Breast")])
    service = CatalogBrowseService(repository, CatalogBrowsePolicy())
    shown = await BrowseCatalogCapability(service, clock=lambda: now).execute(
        input_for(CommerceSession(), {})
    )
    state = shown.session.catalog_browse
    assert state is not None
    invalid = await ResolveCatalogBrowseCapability(service, clock=lambda: now).execute(
        input_for(shown.session, {"navigation": "next"})
    )
    assert invalid.session == shown.session

    selected = product("Previously selected")
    expired_session = shown.session.model_copy(update={"selected_product": selected})
    expired = await ResolveCatalogBrowseCapability(
        service,
        ttl=timedelta(seconds=1),
        clock=lambda: now + timedelta(seconds=2),
    ).execute(input_for(expired_session, {"ordinal": 1}))
    assert expired.session.catalog_browse is None
    assert expired.session.selected_product == selected
    assert expired.outcome.status is ExecutionStatus.NOT_FOUND


def test_resolve_arguments_require_exactly_one_strict_action() -> None:
    ResolveCatalogBrowseArguments(ordinal=1)
    ResolveCatalogBrowseArguments(navigation="next")
    ResolveCatalogBrowseArguments(cancelled=True)
    for data in ({}, {"ordinal": 1, "cancelled": True}, {"ordinal": True}):
        with pytest.raises(ValidationError):
            ResolveCatalogBrowseArguments.model_validate(data)

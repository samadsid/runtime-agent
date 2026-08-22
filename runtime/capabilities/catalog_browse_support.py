from __future__ import annotations

from datetime import datetime

from commerce.models import (
    CatalogBrowseKind,
    CatalogBrowseState,
    CommerceSession,
)
from commerce.services import CatalogBrowseResult, CatalogBrowseResultKind
from runtime.capabilities import CapabilityOutput
from runtime.contracts import (
    ApprovedResponseFragment,
    ExecutionStatus,
    FollowUpRequest,
    GeneratedExecutionOutcome,
    ResponseFragmentKind,
    ResponseIcon,
    ResponseLayout,
)


def browse_result_output(
    session: CommerceSession,
    result: CatalogBrowseResult,
    created_at: datetime,
) -> CapabilityOutput[CommerceSession]:
    if result.kind is CatalogBrowseResultKind.CATEGORIES:
        assert result.categories is not None
        category_page = result.categories
        if not category_page.items:
            return _simple(
                session,
                ExecutionStatus.NOT_FOUND,
                "no-categories-available",
                "No shopping categories are currently available.",
                "request-product-search",
                "What product name would you like me to search for?",
            )
        state = CatalogBrowseState(
            kind=CatalogBrowseKind.CATEGORIES,
            categories=category_page.items,
            page=category_page.page,
            has_previous=category_page.has_previous,
            has_next=category_page.has_next,
            created_at=created_at,
        )
        fragments = (
            ApprovedResponseFragment(
                id="catalog-categories-heading",
                text="Available categories",
                kind=ResponseFragmentKind.SECTION,
            ),
            *tuple(
            ApprovedResponseFragment(
                id=f"catalog-category-{ordinal}",
                text=f"{ordinal}. {item.name}",
                kind=ResponseFragmentKind.ITEM,
            )
            for ordinal, item in enumerate(category_page.items, 1)
            ),
        )
        return CapabilityOutput(
            session=session.model_copy(update={"catalog_browse": state}),
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.SUCCESS,
                fragments=fragments,
                follow_up=FollowUpRequest(
                    id="select-catalog-category",
                    question="Which category would you like to browse?",
                ),
                layout=ResponseLayout.SELECTABLE_LIST,
                heading_emoji=ResponseIcon.CATALOG,
                protected_values=tuple(
                    value
                    for ordinal, item in enumerate(category_page.items, 1)
                    for value in (str(ordinal), item.name)
                ),
            ),
        )
    if result.kind is CatalogBrowseResultKind.PRODUCTS:
        assert result.products is not None
        product_page = result.products
        if not product_page.items:
            return _simple(
                session,
                ExecutionStatus.NOT_FOUND,
                "catalog-empty",
                "The catalog has no products to display.",
                "catalog-empty-follow-up",
                "Would you like to try another catalog request?",
            )
        state = CatalogBrowseState(
            kind=CatalogBrowseKind.PRODUCTS,
            products=product_page.items,
            category_id=product_page.category_id,
            page=product_page.page,
            has_previous=product_page.has_previous,
            has_next=product_page.has_next,
            created_at=created_at,
        )
        fragments = (
            ApprovedResponseFragment(
                id="catalog-products-heading",
                text="Available products",
                kind=ResponseFragmentKind.SECTION,
            ),
            *tuple(
            ApprovedResponseFragment(
                id=f"catalog-product-{ordinal}",
                text=f"{ordinal}. {item.name} - {item.currency} {format(item.price, 'f')}/{item.unit}",
                kind=ResponseFragmentKind.ITEM,
            )
            for ordinal, item in enumerate(product_page.items, 1)
            ),
        )
        return CapabilityOutput(
            session=session.model_copy(update={"catalog_browse": state}),
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.SUCCESS,
                fragments=fragments,
                follow_up=FollowUpRequest(
                    id="select-catalog-product",
                    question="Which product would you like?",
                ),
                layout=ResponseLayout.SELECTABLE_LIST,
                heading_emoji=ResponseIcon.CATALOG,
                protected_values=tuple(
                    value
                    for ordinal, item in enumerate(product_page.items, 1)
                    for value in (
                        str(ordinal),
                        item.name,
                        format(item.price, "f"),
                        item.currency,
                        item.unit,
                    )
                ),
            ),
        )
    if result.kind is CatalogBrowseResultKind.CATEGORY_NOT_FOUND:
        return _simple(
            session,
            ExecutionStatus.NOT_FOUND,
            "catalog-category-not-found",
            "That category was not found in the current catalog.",
            "choose-catalog-category",
            "Which catalog category would you like instead?",
        )
    if result.kind is CatalogBrowseResultKind.CATEGORY_EMPTY:
        assert result.categories is not None
        refreshed = browse_result_output(
            session,
            CatalogBrowseResult(
                kind=CatalogBrowseResultKind.CATEGORIES,
                categories=result.categories,
            ),
            created_at,
        )
        refreshed_outcome = refreshed.outcome
        assert isinstance(refreshed_outcome, GeneratedExecutionOutcome)
        return CapabilityOutput(
            session=refreshed.session,
            outcome=refreshed_outcome.model_copy(
                update={
                    "status": ExecutionStatus.NOT_FOUND,
                    "fragments": (
                        ApprovedResponseFragment(
                            id="category-no-products",
                            text="That category no longer has purchasable products; the category list was refreshed.",
                        ),
                    ) + refreshed_outcome.fragments,
                }
            ),
        )
    return _simple(
        session,
        ExecutionStatus.NOT_FOUND,
        "catalog-empty",
        "The catalog has no available products.",
        "catalog-empty-follow-up",
        "Would you like to try again later?",
    )


def _simple(
    session: CommerceSession,
    status: ExecutionStatus,
    fragment_id: str,
    text: str,
    follow_up_id: str,
    question: str,
) -> CapabilityOutput[CommerceSession]:
    return CapabilityOutput(
        session=session,
        outcome=GeneratedExecutionOutcome(
            status=status,
            fragments=(ApprovedResponseFragment(id=fragment_id, text=text),),
            follow_up=FollowUpRequest(id=follow_up_id, question=question),
        ),
    )


def temporary_failure(session: CommerceSession) -> CapabilityOutput[CommerceSession]:
    return _simple(
        session,
        ExecutionStatus.FAILURE,
        "catalog-temporarily-unavailable",
        "The catalog is temporarily unavailable.",
        "retry-catalog-browse",
        "Would you like to retry browsing?",
    )

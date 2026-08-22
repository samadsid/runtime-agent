from __future__ import annotations

from commerce.models import CommerceSession
from commerce.services import SearchProductService
from runtime.capabilities import (
    Capability,
    CapabilityInput,
    CapabilityMetadata,
    CapabilityOutput,
)
from runtime.contracts import (
    ApprovedResponseFragment,
    ExecutionStatus,
    FollowUpRequest,
    GeneratedExecutionOutcome,
    ResponseFragmentKind,
    ResponseIcon,
    ResponseLayout,
)


class SearchProductCapability(Capability[CommerceSession]):
    def __init__(
        self,
        service: SearchProductService,
    ) -> None:

        self.service = service

    @property
    def metadata(
        self,
    ) -> CapabilityMetadata:

        return CapabilityMetadata(
            name="search_product",
            description=("Searches the product catalog using the customer's query."),
        )

    async def execute(
        self,
        input: CapabilityInput[CommerceSession],
    ) -> CapabilityOutput[CommerceSession]:

        query = str(input.data.get("query", "")).strip()

        if not query:
            return CapabilityOutput(
                session=input.session,
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.MISSING_INPUT,
                    fragments=(
                        ApprovedResponseFragment(
                            id="missing-query",
                            text="I need a product name to search the catalog.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="request-query",
                        question="What product would you like to search for?",
                    ),
                ),
            )

        products = await self.service.search(input.context.tenant_id, query)

        session = input.session.model_copy(
            update={
                "recent_product_results": tuple(products),
                "selected_product": None,
            }
        )

        if not products:
            return CapabilityOutput(
                session=session,
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.NOT_FOUND,
                    fragments=(
                        ApprovedResponseFragment(
                            id="no-results",
                            text=f"I couldn't find any products matching '{query}'.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="refine-query",
                        question=(
                            "What different or more specific product name should I "
                            "search for?"
                        ),
                    ),
                ),
            )

        fragments = [
            ApprovedResponseFragment(
                id="search-results-heading",
                text="Available products:",
                kind=ResponseFragmentKind.SECTION,
            )
        ]
        fragments.extend(
            ApprovedResponseFragment(
                id=f"product-{ordinal}",
                text=f"{ordinal}. {product.name} - ₹{product.price}/{product.unit}",
                kind=ResponseFragmentKind.ITEM,
            )
            for ordinal, product in enumerate(products, start=1)
        )

        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.SUCCESS,
                fragments=tuple(fragments),
                follow_up=FollowUpRequest(
                    id="select-search-product",
                    question="Which product would you like?",
                ),
                layout=ResponseLayout.SELECTABLE_LIST,
                heading_emoji=ResponseIcon.SEARCH,
                protected_values=tuple(
                    value
                    for ordinal, product in enumerate(products, start=1)
                    for value in (
                        str(ordinal),
                        product.name,
                        f"₹{product.price}",
                        product.unit,
                    )
                ),
            ),
        )

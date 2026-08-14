from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from commerce.models import CatalogBrowseKind, CommerceSession
from commerce.services import CatalogBrowseResultKind, CatalogBrowseService
from runtime.capabilities import (
    Capability,
    CapabilityInput,
    CapabilityMetadata,
    CapabilityOutput,
)
from runtime.capabilities.catalog_browse_support import (
    _simple,
    browse_result_output,
    temporary_failure,
)
from runtime.contracts import (
    ApprovedResponseFragment,
    ExecutionStatus,
    FollowUpRequest,
    GeneratedExecutionOutcome,
)


class ResolveCatalogBrowseArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ordinal: int | None = Field(default=None, strict=True, ge=1)
    navigation: Literal["next", "previous"] | None = None
    cancelled: bool = False

    @model_validator(mode="after")
    def exactly_one_action(self) -> ResolveCatalogBrowseArguments:
        if (
            sum((self.ordinal is not None, self.navigation is not None, self.cancelled))
            != 1
        ):
            raise ValueError("Provide exactly one action.")
        return self


class ResolveCatalogBrowseCapability(Capability[CommerceSession]):
    def __init__(
        self,
        service: CatalogBrowseService,
        ttl: timedelta = timedelta(minutes=15),
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._service = service
        self._ttl = ttl
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @property
    def metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            name="resolve_catalog_browse",
            description="Resolves exactly one current browse ordinal, next/previous navigation, or browse cancellation.",
        )

    async def execute(
        self, input: CapabilityInput[CommerceSession]
    ) -> CapabilityOutput[CommerceSession]:
        try:
            arguments = ResolveCatalogBrowseArguments.model_validate(input.data)
        except ValidationError:
            return self._invalid(input.session)
        state = input.session.catalog_browse
        if state is None:
            return _simple(
                input.session,
                ExecutionStatus.NOT_FOUND,
                "catalog-browse-expired",
                "There is no current catalog page to use.",
                "restart-catalog-browse",
                "Would you like to browse the catalog again?",
            )
        if self._clock() - state.created_at > self._ttl:
            return _simple(
                input.session.model_copy(update={"catalog_browse": None}),
                ExecutionStatus.NOT_FOUND,
                "catalog-browse-expired",
                "That catalog page has expired.",
                "restart-catalog-browse",
                "Would you like to browse the catalog again?",
            )
        if arguments.cancelled:
            return CapabilityOutput(
                session=input.session.model_copy(update={"catalog_browse": None}),
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.SUCCESS,
                    fragments=(
                        ApprovedResponseFragment(
                            id="catalog-browse-cancelled",
                            text="Catalog browsing was stopped.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="catalog-next-action",
                        question="What would you like to do next?",
                    ),
                ),
            )
        try:
            if arguments.navigation is not None:
                allowed = (
                    state.has_next
                    if arguments.navigation == "next"
                    else state.has_previous
                )
                if not allowed:
                    return _simple(
                        input.session,
                        ExecutionStatus.INVALID_INPUT,
                        "catalog-page-unavailable",
                        "That catalog page is not available.",
                        "continue-catalog-browse",
                        "Would you like to continue with the current page?",
                    )
                page = state.page + (1 if arguments.navigation == "next" else -1)
                result = await (
                    self._service.categories(input.context.tenant_id, page)
                    if state.kind is CatalogBrowseKind.CATEGORIES
                    else self._service.products(
                        input.context.tenant_id, state.category_id, page
                    )
                )
                return browse_result_output(input.session, result, self._clock())
            assert arguments.ordinal is not None
            if state.kind is CatalogBrowseKind.CATEGORIES:
                if arguments.ordinal > len(state.categories):
                    return self._invalid(input.session)
                result = await self._service.products(
                    input.context.tenant_id,
                    state.categories[arguments.ordinal - 1].category_id,
                    1,
                )
                return browse_result_output(input.session, result, self._clock())
            if arguments.ordinal > len(state.products):
                return self._invalid(input.session)
            result = await self._service.select_product(
                input.context.tenant_id,
                state.products[arguments.ordinal - 1].product_id,
            )
        except Exception:  # noqa: BLE001 - repository failures are customer-safe here
            return temporary_failure(input.session)
        if (
            result.kind is CatalogBrowseResultKind.STALE_PRODUCT
            or result.product is None
        ):
            return _simple(
                input.session,
                ExecutionStatus.NOT_FOUND,
                "catalog-product-stale",
                "That product is no longer available.",
                "restart-catalog-browse",
                "Would you like to browse current products?",
            )
        product = result.product
        session = input.session.model_copy(
            update={
                "catalog_browse": None,
                "selected_product": product,
                "recent_product_results": (product,),
            }
        )
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.SUCCESS,
                fragments=(
                    ApprovedResponseFragment(
                        id="selected-product", text=f"Selected {product.name}."
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="quantity-request",
                    question="Please specify the quantity you would like to order.",
                ),
                protected_values=(product.name,),
            ),
        )

    @staticmethod
    def _invalid(session: CommerceSession) -> CapabilityOutput[CommerceSession]:
        return _simple(
            session,
            ExecutionStatus.INVALID_INPUT,
            "invalid-catalog-ordinal",
            "That number does not match the current catalog page.",
            "correct-catalog-ordinal",
            "Which number from the current page would you like?",
        )

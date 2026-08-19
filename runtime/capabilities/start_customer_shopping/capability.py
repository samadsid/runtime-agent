from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, ValidationError

from commerce.models import CommerceSession, CustomerEntryKind
from commerce.services import CatalogBrowseService
from runtime.capabilities import (
    Capability,
    CapabilityInput,
    CapabilityMetadata,
    CapabilityName,
    CapabilityOutput,
)
from runtime.capabilities.catalog_browse_support import (
    browse_result_output,
    temporary_failure,
)
from runtime.contracts import (
    ApprovedResponseFragment,
    ExecutionStatus,
    GeneratedExecutionOutcome,
)
from runtime.observability import CustomerJourneyObserver, NullCustomerJourneyObserver


class StartCustomerShoppingArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StartCustomerShoppingCapability(Capability[CommerceSession]):
    def __init__(
        self,
        service: CatalogBrowseService,
        observer: CustomerJourneyObserver | None = None,
    ) -> None:
        self._service = service
        self._observer = observer or NullCustomerJourneyObserver()

    @property
    def metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            name=CapabilityName.START_CUSTOMER_SHOPPING,
            description="Greets an onboarded customer and shows the first authoritative category page; takes no arguments.",
        )

    async def execute(
        self, input: CapabilityInput[CommerceSession]
    ) -> CapabilityOutput[CommerceSession]:
        try:
            StartCustomerShoppingArguments.model_validate(input.data)
        except ValidationError:
            return CapabilityOutput(
                session=input.session,
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.FAILURE,
                    fragments=(
                        ApprovedResponseFragment(
                            id="invalid-customer-shopping-entry",
                            text="That shopping request is invalid.",
                        ),
                    ),
                ),
            )
        if not input.context.profile.onboarding_completed:
            return CapabilityOutput(
                session=input.session,
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.FAILURE,
                    fragments=(
                        ApprovedResponseFragment(
                            id="customer-shopping-entry-unavailable",
                            text="Customer onboarding must be completed before starting the saved-customer shopping journey.",
                        ),
                    ),
                ),
            )
        try:
            result = await self._service.categories(input.context.tenant_id, 1)
        except Exception:  # noqa: BLE001
            self._observer.category_view("failure")
            return temporary_failure(input.session)
        self._observer.category_view("success")
        shown = browse_result_output(input.session, result, datetime.now(timezone.utc))
        outcome = shown.outcome
        assert isinstance(outcome, GeneratedExecutionOutcome)
        if input.context.profile.entry_kind is not CustomerEntryKind.RETURNING:
            return shown
        greeting = ApprovedResponseFragment(
            id="returning-customer-welcome",
            text=(
                f"Welcome back, {input.context.profile.preferred_name}."
                if input.context.profile.preferred_name
                else "Welcome back."
            ),
        )
        return CapabilityOutput(
            session=shown.session,
            outcome=outcome.model_copy(
                update={
                    "fragments": (greeting,) + outcome.fragments,
                    "protected_values": (
                        (input.context.profile.preferred_name,)
                        if input.context.profile.preferred_name
                        else ()
                    )
                    + outcome.protected_values,
                }
            ),
        )

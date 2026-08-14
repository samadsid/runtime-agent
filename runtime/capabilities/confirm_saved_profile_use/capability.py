from __future__ import annotations

from pydantic import BaseModel, ConfigDict, StrictBool, ValidationError

from commerce.models import CheckoutStage, CommerceSession
from commerce.services import SavedDeliveryDetailsService
from runtime.capabilities import (
    Capability,
    CapabilityInput,
    CapabilityMetadata,
    CapabilityName,
    CapabilityOutput,
)
from runtime.capabilities.checkout_support import (
    confirmation_review_outcome,
    missing_detail_outcome,
    next_missing_detail,
)
from runtime.capabilities.saved_delivery_support import stale_saved_address
from runtime.contracts import (
    ApprovedResponseFragment,
    ExecutionStatus,
    FollowUpRequest,
    GeneratedExecutionOutcome,
)


class ConfirmSavedProfileUseArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed: StrictBool


class ConfirmSavedProfileUseCapability(Capability[CommerceSession]):
    def __init__(self, service: SavedDeliveryDetailsService) -> None:
        self._service = service

    @property
    def metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            name=CapabilityName.CONFIRM_SAVED_PROFILE_USE,
            description=(
                "Accepts or declines the exact pending saved delivery-detail offer. "
                "Requires a boolean 'confirmed' argument."
            ),
        )

    async def execute(
        self, input: CapabilityInput[CommerceSession]
    ) -> CapabilityOutput[CommerceSession]:
        pending = input.session.pending_saved_profile_use
        try:
            arguments = ConfirmSavedProfileUseArguments.model_validate(input.data)
        except ValidationError:
            arguments = None
        if arguments is None:
            return CapabilityOutput(
                session=input.session,
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.INVALID_INPUT,
                    fragments=(
                        ApprovedResponseFragment(
                            id="saved-profile-confirmation-invalid",
                            text="The saved-detail confirmation was not understood.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="clarify-saved-profile-use",
                        question="Would you like to use the offered saved details?",
                    ),
                ),
            )
        if pending is None:
            checkout = input.session.checkout
            complete = all(
                (
                    checkout.customer_name,
                    checkout.phone_number,
                    checkout.delivery_address,
                )
            )
            if complete:
                checkout = checkout.model_copy(
                    update={"stage": CheckoutStage.READY_TO_CONFIRM}
                )
                session = input.session.model_copy(update={"checkout": checkout})
                return CapabilityOutput(
                    session=session,
                    outcome=confirmation_review_outcome(checkout),
                )
            missing = next_missing_detail(checkout)
            if missing is not None:
                return CapabilityOutput(
                    session=input.session,
                    outcome=missing_detail_outcome(checkout),
                )
            raise AssertionError("Incomplete checkout must have a missing detail.")
        session = input.session.model_copy(update={"pending_saved_profile_use": None})
        if not arguments.confirmed:
            return CapabilityOutput(
                session=session, outcome=missing_detail_outcome(session.checkout)
            )
        context = input.context
        profile = await self._service.get_profile(
            context.tenant_id, context.channel, context.channel_customer_id
        )
        address = (
            await self._service.get_address(
                context.tenant_id, pending.profile_id, pending.address_id
            )
            if pending.address_id is not None
            else None
        )
        if (
            profile is None
            or profile.id != pending.profile_id
            or (
                pending.customer_name is not None
                and profile.customer_name != pending.customer_name
            )
            or (
                pending.phone_number is not None
                and profile.phone_number != pending.phone_number
            )
            or (
                pending.address_id is not None
                and (
                    address is None
                    or address.delivery_address != pending.delivery_address
                )
            )
        ):
            return stale_saved_address(session)
        checkout = session.checkout
        checkout = checkout.model_copy(
            update={
                "customer_name": checkout.customer_name or pending.customer_name,
                "phone_number": checkout.phone_number or pending.phone_number,
                "delivery_address": (
                    checkout.delivery_address or pending.delivery_address
                ),
            }
        )
        if all(
            (
                checkout.customer_name,
                checkout.phone_number,
                checkout.delivery_address,
            )
        ):
            checkout = checkout.model_copy(
                update={"stage": CheckoutStage.READY_TO_CONFIRM}
            )
        session = session.model_copy(update={"checkout": checkout})
        outcome = (
            confirmation_review_outcome(checkout)
            if all(
                (
                    checkout.customer_name,
                    checkout.phone_number,
                    checkout.delivery_address,
                )
            )
            else missing_detail_outcome(checkout)
        )
        return CapabilityOutput(session=session, outcome=outcome)

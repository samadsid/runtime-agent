from __future__ import annotations

from pydantic import BaseModel, ConfigDict, StrictBool, ValidationError

from commerce.models import CommerceSession
from commerce.repositories import SavedDeliveryProfileConflictError
from commerce.services import SavedDeliveryDetailsService
from runtime.capabilities import (
    Capability,
    CapabilityInput,
    CapabilityMetadata,
    CapabilityName,
    CapabilityOutput,
)
from runtime.contracts import (
    ApprovedResponseFragment,
    ExecutionStatus,
    FollowUpRequest,
    GeneratedExecutionOutcome,
)


class ConfirmSaveDeliveryDetailsArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed: StrictBool


class ConfirmSaveDeliveryDetailsCapability(Capability[CommerceSession]):
    def __init__(self, service: SavedDeliveryDetailsService) -> None:
        self._service = service

    @property
    def metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            name=CapabilityName.CONFIRM_SAVE_DELIVERY_DETAILS,
            description="Confirms or declines the exact pending saved-delivery proposal.",
        )

    async def execute(
        self, input: CapabilityInput[CommerceSession]
    ) -> CapabilityOutput[CommerceSession]:
        pending = input.session.pending_saved_details_save
        try:
            arguments = ConfirmSaveDeliveryDetailsArguments.model_validate(input.data)
        except ValidationError:
            arguments = None
        if pending is None or arguments is None:
            return CapabilityOutput(
                session=input.session,
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.INVALID_INPUT,
                    fragments=(
                        ApprovedResponseFragment(
                            id="no-pending-saved-details",
                            text="There are no pending saved delivery details to confirm.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="request-save-details",
                        question="Which delivery details would you like to save?",
                    ),
                ),
            )
        cleared = input.session.model_copy(update={"pending_saved_details_save": None})
        if not arguments.confirmed:
            return CapabilityOutput(
                session=cleared,
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.SUCCESS,
                    fragments=(
                        ApprovedResponseFragment(
                            id="delivery-details-save-declined",
                            text="The delivery details were not saved.",
                        ),
                    ),
                ),
            )
        context = input.context
        try:
            await self._service.save_details(
                context.tenant_id,
                context.channel,
                context.channel_customer_id,
                pending.customer_name,
                pending.phone_number,
                pending.address_label,
                pending.delivery_address,
                pending.set_as_default,
                (
                    (pending.expected_customer_name, pending.expected_phone_number)
                    if pending.profile_existed
                    else None
                ),
                expect_profile_absent=not pending.profile_existed,
            )
        except SavedDeliveryProfileConflictError:
            return CapabilityOutput(
                session=cleared.model_copy(update={"recent_saved_addresses": ()}),
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.CONFLICT,
                    fragments=(
                        ApprovedResponseFragment(
                            id="saved-details-changed",
                            text="The saved profile changed before confirmation, so nothing was overwritten.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="review-saved-details",
                        question="Would you like to review and save the details again?",
                    ),
                ),
            )
        return CapabilityOutput(
            session=cleared.model_copy(update={"recent_saved_addresses": ()}),
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.SUCCESS,
                fragments=(
                    ApprovedResponseFragment(
                        id="delivery-details-saved",
                        text="The delivery details were saved.",
                    ),
                ),
            ),
        )

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from commerce.models import (
    CommerceSession,
    PendingSavedDetailsSave,
    SavedDetailsConfirmationReason,
)
from commerce.services import (
    InvalidSavedDeliveryDetailsError,
    SavedDeliveryDetailsService,
)
from runtime.capabilities import (
    Capability,
    CapabilityInput,
    CapabilityMetadata,
    CapabilityName,
    CapabilityOutput,
)
from runtime.capabilities.checkout_support import NonEmptyText
from runtime.capabilities.saved_delivery_support import guest_unavailable
from runtime.contracts import (
    ApprovedResponseFragment,
    ExecutionStatus,
    FollowUpRequest,
    GeneratedExecutionOutcome,
)


class SaveDeliveryDetailsArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_name: NonEmptyText | None = None
    phone_number: NonEmptyText | None = None
    address_label: NonEmptyText | None = None
    delivery_address: NonEmptyText | None = None
    set_as_default: bool = False
    consent: Literal[True] | None = None


class SaveDeliveryDetailsCapability(Capability[CommerceSession]):
    def __init__(self, service: SavedDeliveryDetailsService) -> None:
        self._service = service

    @property
    def metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            name=CapabilityName.SAVE_DELIVERY_DETAILS,
            description="Saves explicitly consented delivery details for the trusted channel customer.",
        )

    async def execute(
        self, input: CapabilityInput[CommerceSession]
    ) -> CapabilityOutput[CommerceSession]:
        context = input.context
        if context.channel_customer_id is None:
            return guest_unavailable(input.session)
        try:
            arguments = SaveDeliveryDetailsArguments.model_validate(input.data)
            proposal = self._proposal(input.session, arguments)
            self._service.validate_details(
                proposal["customer_name"],
                proposal["phone_number"],
                proposal["address_label"],
                proposal["delivery_address"],
            )
        except (ValidationError, InvalidSavedDeliveryDetailsError):
            return self._invalid(input.session)
        profile = await self._service.get_profile(
            context.tenant_id, context.channel, context.channel_customer_id
        )
        pending = PendingSavedDetailsSave(
            reason=SavedDetailsConfirmationReason.CONSENT,
            **proposal,
            profile_existed=profile is not None,
            expected_customer_name=profile.customer_name if profile else None,
            expected_phone_number=profile.phone_number if profile else None,
        )
        if arguments.consent is not True:
            return self._confirmation_required(input.session, pending, overwrite=False)
        differs = profile is not None and any(
            proposed is not None and current is not None and proposed != current
            for proposed, current in (
                (proposal["customer_name"], profile.customer_name),
                (proposal["phone_number"], profile.phone_number),
            )
        )
        if differs:
            pending = pending.model_copy(
                update={"reason": SavedDetailsConfirmationReason.OVERWRITE}
            )
            return self._confirmation_required(input.session, pending, overwrite=True)
        return await self._persist(input, pending)

    def _proposal(
        self, session: CommerceSession, arguments: SaveDeliveryDetailsArguments
    ) -> dict[str, object]:
        checkout = session.checkout
        customer_name = arguments.customer_name or checkout.customer_name
        phone_number = arguments.phone_number or checkout.phone_number
        delivery_address = arguments.delivery_address
        if arguments.address_label is not None:
            delivery_address = delivery_address or checkout.delivery_address
        elif delivery_address is not None:
            raise InvalidSavedDeliveryDetailsError("An address label is required.")
        if arguments.set_as_default and delivery_address is None:
            raise InvalidSavedDeliveryDetailsError(
                "A saved address is required for default selection."
            )
        if not any((customer_name, phone_number, delivery_address)):
            raise InvalidSavedDeliveryDetailsError("No details are available to save.")
        return {
            "customer_name": customer_name,
            "phone_number": phone_number,
            "address_label": arguments.address_label,
            "delivery_address": delivery_address,
            "set_as_default": arguments.set_as_default,
        }

    async def _persist(
        self, input: CapabilityInput[CommerceSession], pending: PendingSavedDetailsSave
    ) -> CapabilityOutput[CommerceSession]:
        context = input.context
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
        return CapabilityOutput(
            session=input.session.model_copy(
                update={
                    "recent_saved_addresses": (),
                    "pending_saved_details_save": None,
                }
            ),
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

    @staticmethod
    def _confirmation_required(
        session: CommerceSession, pending: PendingSavedDetailsSave, overwrite: bool
    ) -> CapabilityOutput[CommerceSession]:
        return CapabilityOutput(
            session=session.model_copy(update={"pending_saved_details_save": pending}),
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.CONFLICT
                if overwrite
                else ExecutionStatus.MISSING_INPUT,
                fragments=(
                    ApprovedResponseFragment(
                        id="saved-details-differ"
                        if overwrite
                        else "delivery-details-not-saved",
                        text="The proposed details differ from saved values and have not been overwritten."
                        if overwrite
                        else "The delivery details have not been saved without explicit consent.",
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="confirm-saved-details-overwrite"
                    if overwrite
                    else "confirm-save-delivery-details",
                    question="Do you explicitly confirm overwriting the differing saved details?"
                    if overwrite
                    else "Do you explicitly consent to saving these delivery details?",
                ),
            ),
        )

    @staticmethod
    def _invalid(session: CommerceSession) -> CapabilityOutput[CommerceSession]:
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.INVALID_INPUT,
                fragments=(
                    ApprovedResponseFragment(
                        id="invalid-saved-delivery-details",
                        text="The delivery details could not be saved as supplied.",
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="correct-saved-delivery-details",
                    question="What valid delivery details and address label would you like to save?",
                ),
            ),
        )

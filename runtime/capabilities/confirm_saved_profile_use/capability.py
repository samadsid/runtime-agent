from __future__ import annotations

from pydantic import BaseModel, ConfigDict, StrictBool, ValidationError

from commerce.models import CommerceSession, PaymentMethod
from commerce.services import (
    ConfiguredPaymentMethodPolicy,
    PaymentMethodPolicy,
    SavedDeliveryDetailsService,
)
from runtime.capabilities import (
    Capability,
    CapabilityInput,
    CapabilityMetadata,
    CapabilityName,
    CapabilityOutput,
)
from runtime.capabilities.checkout_support import (
    advance_to_payment,
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
    def __init__(
        self,
        service: SavedDeliveryDetailsService,
        payment_policy: PaymentMethodPolicy | None = None,
    ) -> None:
        self._service = service
        self._payment_policy = payment_policy or ConfiguredPaymentMethodPolicy(
            (PaymentMethod.CASH_ON_DELIVERY,), online_operational=False
        )

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
                checkout, outcome = await advance_to_payment(
                    checkout,
                    input.session.cart_items,
                    input.context.tenant_id,
                    self._payment_policy,
                )
                session = input.session.model_copy(update={"checkout": checkout})
                return CapabilityOutput(session=session, outcome=outcome)
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
            checkout, outcome = await advance_to_payment(
                checkout,
                session.cart_items,
                input.context.tenant_id,
                self._payment_policy,
            )
        else:
            outcome = missing_detail_outcome(checkout)
        session = session.model_copy(update={"checkout": checkout})
        return CapabilityOutput(session=session, outcome=outcome)

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from commerce.models import (
    CheckoutStage,
    CommerceSession,
    PaymentMethod,
    PendingSavedProfileUse,
)
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
)
from runtime.capabilities.saved_delivery_support import (
    invalid_saved_address_ordinal,
    resolve_option,
    stale_saved_address,
)
from runtime.contracts import (
    ApprovedResponseFragment,
    ExecutionStatus,
    FollowUpRequest,
    GeneratedExecutionOutcome,
)


class SelectSavedAddressArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ordinal: int = Field(strict=True, ge=1)


class SelectSavedAddressCapability(Capability[CommerceSession]):
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
            name=CapabilityName.SELECT_SAVED_ADDRESS,
            description="Selects a recently listed saved address for active checkout.",
        )

    async def execute(
        self, input: CapabilityInput[CommerceSession]
    ) -> CapabilityOutput[CommerceSession]:
        try:
            arguments = SelectSavedAddressArguments.model_validate(input.data)
        except ValidationError:
            return invalid_saved_address_ordinal(input.session)
        option = resolve_option(input.session, arguments.ordinal)
        if option is None:
            return invalid_saved_address_ordinal(input.session)
        checkout = input.session.checkout
        if checkout.stage not in {
            CheckoutStage.COLLECTING_DETAILS,
            CheckoutStage.READY_TO_CONFIRM,
        }:
            return CapabilityOutput(
                session=input.session,
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.INVALID_INPUT,
                    fragments=(
                        ApprovedResponseFragment(
                            id="checkout-not-collecting",
                            text="Checkout is not ready to use a saved address.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="start-checkout",
                        question="Would you like to start checkout?",
                    ),
                ),
            )
        context = input.context
        profile = await self._service.get_profile(
            context.tenant_id, context.channel, context.channel_customer_id
        )
        if profile is None:
            return stale_saved_address(input.session)
        address = await self._service.get_address(
            context.tenant_id, profile.id, option.address_id
        )
        if address is None:
            return stale_saved_address(input.session)
        checkout = checkout.model_copy(
            update={"delivery_address": address.delivery_address}
        )
        offered_name = profile.customer_name if checkout.customer_name is None else None
        offered_phone = profile.phone_number if checkout.phone_number is None else None
        session = input.session.model_copy(update={"checkout": checkout})
        if offered_name is not None or offered_phone is not None:
            pending = PendingSavedProfileUse(
                profile_id=profile.id,
                customer_name=offered_name,
                phone_number=offered_phone,
            )
            fragments = [
                ApprovedResponseFragment(
                    id="saved-address-selected",
                    text=f"Saved address {arguments.ordinal} ({address.label}) was selected.",
                )
            ]
            protected = [str(arguments.ordinal), address.label]
            if offered_name is not None:
                fragments.append(
                    ApprovedResponseFragment(
                        id="saved-profile-name-available",
                        text=f"Saved name available: {offered_name}",
                    )
                )
                protected.append(offered_name)
            if offered_phone is not None:
                masked = self._mask_phone(offered_phone)
                fragments.append(
                    ApprovedResponseFragment(
                        id="saved-profile-phone-available",
                        text=f"Saved phone available: {masked}",
                    )
                )
                protected.append(masked)
            return CapabilityOutput(
                session=session.model_copy(
                    update={"pending_saved_profile_use": pending}
                ),
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.MISSING_INPUT,
                    fragments=tuple(fragments),
                    follow_up=FollowUpRequest(
                        id="confirm-saved-profile-use",
                        question="Would you like to use the offered saved name and phone for this checkout?",
                    ),
                    protected_values=tuple(protected),
                ),
            )
        session = session.model_copy(update={"pending_saved_profile_use": None})
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
            session = session.model_copy(update={"checkout": checkout})
        else:
            outcome = missing_detail_outcome(checkout)
        return CapabilityOutput(session=session, outcome=outcome)

    @staticmethod
    def _mask_phone(phone: str) -> str:
        return f"{'*' * max(0, len(phone) - 4)}{phone[-4:]}"

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, ValidationError

from commerce.models import CheckoutStage, CommerceSession, PaymentMethod
from commerce.services import (
    ConfiguredPaymentMethodPolicy,
    PaymentMethodPolicy,
    PhoneValidationPolicy,
)
from runtime.capabilities import (
    Capability,
    CapabilityInput,
    CapabilityMetadata,
    CapabilityName,
    CapabilityOutput,
)
from runtime.capabilities.checkout_support import (
    NonEmptyText,
    advance_to_payment,
    missing_detail_outcome,
    next_missing_detail,
)
from runtime.contracts import (
    ApprovedResponseFragment,
    ExecutionStatus,
    FollowUpRequest,
    GeneratedExecutionOutcome,
)


class DeliveryDetailsArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_name: NonEmptyText | None = None
    phone_number: NonEmptyText | None = None
    delivery_address: NonEmptyText | None = None


class CollectDeliveryDetailsCapability(Capability[CommerceSession]):
    def __init__(
        self,
        phone_policy: PhoneValidationPolicy,
        payment_policy: PaymentMethodPolicy | None = None,
    ) -> None:
        self._phone_policy = phone_policy
        self._payment_policy = payment_policy or ConfiguredPaymentMethodPolicy(
            (PaymentMethod.CASH_ON_DELIVERY,), online_operational=False
        )

    @property
    def metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            name=CapabilityName.COLLECT_DELIVERY_DETAILS,
            description=(
                "Collects any supplied customer name, phone number, and delivery "
                "address while checkout is collecting details."
            ),
        )

    async def execute(
        self, input: CapabilityInput[CommerceSession]
    ) -> CapabilityOutput[CommerceSession]:
        checkout = input.session.checkout
        if checkout.stage not in {
            CheckoutStage.COLLECTING_DETAILS,
            CheckoutStage.READY_TO_CONFIRM,
        }:
            return self._not_collecting(input.session)

        try:
            arguments = DeliveryDetailsArguments.model_validate(input.data)
        except ValidationError as error:
            location = error.errors()[0].get("loc", ())
            field = location[0] if location else None
            return self._invalid_detail(
                input.session, field if isinstance(field, str) else None
            )

        if any(
            field in arguments.model_fields_set and getattr(arguments, field) is None
            for field in (
                "customer_name",
                "phone_number",
                "delivery_address",
            )
        ):
            invalid_field = next(
                field
                for field in (
                    "customer_name",
                    "phone_number",
                    "delivery_address",
                )
                if field in arguments.model_fields_set
                and getattr(arguments, field) is None
            )
            return self._invalid_detail(input.session, invalid_field)

        if arguments.phone_number is not None and not self._phone_policy.is_valid(
            arguments.phone_number
        ):
            return self._invalid_phone(input.session)

        updates = {
            field: value
            for field, value in arguments.model_dump().items()
            if value is not None
        }
        checkout = checkout.model_copy(update=updates)
        missing = next_missing_detail(checkout)
        if missing is None:
            checkout, outcome = await advance_to_payment(
                checkout,
                input.session.cart_items,
                input.context.tenant_id,
                self._payment_policy,
            )
        else:
            checkout = checkout.model_copy(
                update={"stage": CheckoutStage.COLLECTING_DETAILS}
            )
            outcome = missing_detail_outcome(checkout)

        return CapabilityOutput(
            session=input.session.model_copy(
                update={"checkout": checkout, "pending_saved_profile_use": None}
            ),
            outcome=outcome,
        )

    @staticmethod
    def _not_collecting(session: CommerceSession) -> CapabilityOutput[CommerceSession]:
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.INVALID_INPUT,
                fragments=(
                    ApprovedResponseFragment(
                        id="checkout-not-collecting",
                        text="Checkout is not ready to collect delivery details.",
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="start-checkout", question="Would you like to start checkout?"
                ),
            ),
        )

    @staticmethod
    def _invalid_detail(
        session: CommerceSession, field: str | None = None
    ) -> CapabilityOutput[CommerceSession]:
        questions = {
            "customer_name": "What name should I use for this order?",
            "phone_number": "What phone number should I use for delivery?",
            "delivery_address": "What is the complete delivery address?",
        }
        missing = next_missing_detail(session.checkout)
        question = questions.get(
            field,
            missing[1]
            if missing is not None
            else "Which delivery detail would you like to correct?",
        )
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.INVALID_INPUT,
                fragments=(
                    ApprovedResponseFragment(
                        id="invalid-delivery-detail",
                        text="Please provide a non-empty delivery detail.",
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="correct-delivery-detail", question=question
                ),
            ),
        )

    @staticmethod
    def _invalid_phone(session: CommerceSession) -> CapabilityOutput[CommerceSession]:
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.INVALID_INPUT,
                fragments=(
                    ApprovedResponseFragment(
                        id="invalid-phone-number",
                        text="That phone number does not satisfy the delivery policy.",
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="correct-phone-number",
                    question="What phone number should I use for delivery?",
                ),
            ),
        )

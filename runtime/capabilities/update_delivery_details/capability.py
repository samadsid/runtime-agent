from __future__ import annotations

from pydantic import BaseModel, ConfigDict, ValidationError

from commerce.models import (
    Cart,
    CheckoutStage,
    CheckoutState,
    CommerceSession,
    DeliveryDetailField,
    PaymentMethod,
)
from commerce.services import (
    CartService,
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


class UpdateDeliveryDetailsArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_field: DeliveryDetailField | None = None
    customer_name: NonEmptyText | None = None
    phone_number: NonEmptyText | None = None
    delivery_address: NonEmptyText | None = None


class UpdateDeliveryDetailsCapability(Capability[CommerceSession]):
    _detail_fields = (
        DeliveryDetailField.CUSTOMER_NAME,
        DeliveryDetailField.PHONE_NUMBER,
        DeliveryDetailField.DELIVERY_ADDRESS,
    )

    def __init__(
        self,
        cart_service: CartService,
        phone_policy: PhoneValidationPolicy,
        payment_policy: PaymentMethodPolicy | None = None,
    ) -> None:
        self._cart_service = cart_service
        self._phone_policy = phone_policy
        self._payment_policy = payment_policy or ConfiguredPaymentMethodPolicy(
            (PaymentMethod.CASH_ON_DELIVERY,), online_operational=False
        )

    @property
    def metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            name=CapabilityName.UPDATE_DELIVERY_DETAILS,
            description=(
                "Corrects one or more checkout delivery details, or records the "
                "named field whose replacement should be collected next."
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
            return self._not_active(input.session)

        try:
            arguments = UpdateDeliveryDetailsArguments.model_validate(input.data)
        except ValidationError as error:
            location = error.errors()[0].get("loc", ())
            field = location[0] if location else None
            return self._invalid_detail(
                input.session, field if isinstance(field, str) else None
            )

        supplied_fields = tuple(
            field
            for field in self._detail_fields
            if field.value in arguments.model_fields_set
            and getattr(arguments, field.value) is not None
        )
        explicitly_empty = next(
            (
                field
                for field in self._detail_fields
                if field.value in arguments.model_fields_set
                and getattr(arguments, field.value) is None
            ),
            None,
        )
        if explicitly_empty is not None:
            return self._invalid_detail(input.session, explicitly_empty.value)

        if not supplied_fields and arguments.requested_field is None:
            pending = checkout.pending_delivery_correction
            return self._invalid_detail(
                input.session, pending.value if pending is not None else None
            )

        cart = await self._cart_service.get_active(
            input.context.tenant_id, input.context.conversation_id
        )
        if (
            checkout.source_cart_id is None
            or cart is None
            or not cart.items
            or cart.id != checkout.source_cart_id
        ):
            return self._stale_checkout(input.session, cart)

        refreshed_session = input.session.model_copy(update={"cart_items": cart.items})

        if not supplied_fields:
            requested_field = arguments.requested_field
            if requested_field is None:
                raise AssertionError("A requested delivery field is required.")
            checkout = checkout.model_copy(
                update={"pending_delivery_correction": requested_field}
            )
            return CapabilityOutput(
                session=refreshed_session.model_copy(update={"checkout": checkout}),
                outcome=self._replacement_required(requested_field),
            )

        if arguments.phone_number is not None and not self._phone_policy.is_valid(
            arguments.phone_number
        ):
            return self._invalid_phone(refreshed_session)

        updates = {
            field.value: getattr(arguments, field.value) for field in supplied_fields
        }
        updates["pending_delivery_correction"] = None
        checkout = checkout.model_copy(update=updates)
        missing = next_missing_detail(checkout)
        if missing is None:
            checkout, outcome = await advance_to_payment(
                checkout,
                cart.items,
                input.context.tenant_id,
                self._payment_policy,
                corrected=True,
            )
        else:
            checkout = checkout.model_copy(
                update={"stage": CheckoutStage.COLLECTING_DETAILS}
            )
            outcome = missing_detail_outcome(checkout).model_copy(
                update={
                    "fragments": (
                        ApprovedResponseFragment(
                            id="delivery-detail-corrected",
                            text="The supplied delivery detail was corrected.",
                        ),
                    )
                }
            )

        return CapabilityOutput(
            session=refreshed_session.model_copy(
                update={"checkout": checkout, "pending_saved_profile_use": None}
            ),
            outcome=outcome,
        )

    @staticmethod
    def _replacement_required(
        field: DeliveryDetailField,
    ) -> GeneratedExecutionOutcome:
        questions = {
            DeliveryDetailField.CUSTOMER_NAME: "What name should I use for this order?",
            DeliveryDetailField.PHONE_NUMBER: (
                "What phone number should I use for delivery?"
            ),
            DeliveryDetailField.DELIVERY_ADDRESS: "What is the new delivery address?",
        }
        return GeneratedExecutionOutcome(
            status=ExecutionStatus.MISSING_INPUT,
            fragments=(
                ApprovedResponseFragment(
                    id="delivery-detail-correction-requested",
                    text=f"A replacement {field.value} is required.",
                ),
            ),
            follow_up=FollowUpRequest(
                id="request-corrected-delivery-detail", question=questions[field]
            ),
        )

    @staticmethod
    def _not_active(session: CommerceSession) -> CapabilityOutput[CommerceSession]:
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.INVALID_INPUT,
                fragments=(
                    ApprovedResponseFragment(
                        id="checkout-not-collecting",
                        text="Checkout is not collecting or reviewing delivery details.",
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="start-checkout", question="Would you like to start checkout?"
                ),
            ),
        )

    @staticmethod
    def _invalid_detail(
        session: CommerceSession, field: str | None
    ) -> CapabilityOutput[CommerceSession]:
        questions = {
            "customer_name": "What name should I use for this order?",
            "phone_number": "What phone number should I use for delivery?",
            "delivery_address": "What is the new delivery address?",
        }
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.INVALID_INPUT,
                fragments=(
                    ApprovedResponseFragment(
                        id="invalid-delivery-detail-correction",
                        text="The delivery-detail correction was not valid.",
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="correct-delivery-detail",
                    question=questions.get(
                        field or "",
                        "Which delivery detail would you like to correct?",
                    ),
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
                        id="invalid-corrected-phone-number",
                        text="That phone number does not satisfy the delivery policy.",
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="correct-phone-number",
                    question="What phone number should I use for delivery?",
                ),
            ),
        )

    @staticmethod
    def _stale_checkout(
        session: CommerceSession, cart: Cart | None
    ) -> CapabilityOutput[CommerceSession]:
        cart_items = cart.items if cart is not None else ()
        reset_session = session.model_copy(
            update={
                "cart_items": cart_items,
                "checkout": CheckoutState(),
                "pending_saved_profile_use": None,
            }
        )
        return CapabilityOutput(
            session=reset_session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.NOT_FOUND,
                fragments=(
                    ApprovedResponseFragment(
                        id="stale-checkout",
                        text="The checkout cart is no longer active for this review.",
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="restart-checkout",
                    question="Would you like to review the current cart and restart checkout?",
                ),
            ),
        )

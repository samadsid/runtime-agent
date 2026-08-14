from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from commerce.models import CommerceSession
from commerce.services import PaymentService
from runtime.capabilities import (
    Capability,
    CapabilityInput,
    CapabilityMetadata,
    CapabilityName,
    CapabilityOutput,
)
from runtime.capabilities.checkout_support import payment_method_label
from runtime.contracts import (
    ApprovedResponseFragment,
    ExecutionStatus,
    FollowUpRequest,
    GeneratedExecutionOutcome,
)


class SwitchArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed: Literal[True]


class SwitchOrderToCashOnDeliveryCapability(Capability[CommerceSession]):
    def __init__(self, service: PaymentService) -> None:
        self._service = service

    @property
    def metadata(self):
        return CapabilityMetadata(
            name=CapabilityName.SWITCH_ORDER_TO_CASH_ON_DELIVERY,
            description="Switches the current provisional online order to COD only with confirmed=true.",
        )

    async def execute(self, input: CapabilityInput[CommerceSession]):
        try:
            SwitchArguments.model_validate(input.data)
        except ValidationError:
            return CapabilityOutput(
                session=input.session,
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.INVALID_INPUT,
                    fragments=(
                        ApprovedResponseFragment(
                            id="cod-switch-confirmation-required",
                            text="The payment method was not changed without explicit confirmation.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="confirm-cod-switch",
                        question="Do you explicitly confirm switching this order to cash on delivery?",
                    ),
                ),
            )
        try:
            order = await self._service.switch_to_cod(
                input.context.tenant_id, input.context.conversation_id
            )
        except (LookupError, ValueError, RuntimeError):
            return CapabilityOutput(
                session=input.session,
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.FAILURE,
                    fragments=(
                        ApprovedResponseFragment(
                            id="payment-status-unavailable",
                            text="The order cannot safely switch to cash on delivery right now.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="check-payment-status",
                        question="Would you like to check payment status first?",
                    ),
                ),
            )
        return CapabilityOutput(
            session=input.session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.SUCCESS,
                fragments=(
                    ApprovedResponseFragment(
                        id="switched-to-cash-on-delivery",
                        text=(
                            f"Order {order.id} is {order.status.value} with "
                            f"{payment_method_label(order.payment_method)}."
                        ),
                    ),
                ),
                protected_values=(
                    str(order.id),
                    order.status.value,
                    payment_method_label(order.payment_method),
                ),
            ),
        )

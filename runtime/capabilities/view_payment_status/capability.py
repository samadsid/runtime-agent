from commerce.models import CommerceSession
from commerce.services import PaymentService
from runtime.capabilities import (
    Capability,
    CapabilityInput,
    CapabilityMetadata,
    CapabilityName,
    CapabilityOutput,
)
from runtime.capabilities.payment_support import payment_outcome
from runtime.contracts import (
    ApprovedResponseFragment,
    ExecutionStatus,
    FollowUpRequest,
    GeneratedExecutionOutcome,
)


class ViewPaymentStatusCapability(Capability[CommerceSession]):
    def __init__(self, service: PaymentService) -> None:
        self._service = service

    @property
    def metadata(self):
        return CapabilityMetadata(
            name=CapabilityName.VIEW_PAYMENT_STATUS,
            description="Returns safe payment status for the latest owned online order; accepts no provider or payment ID.",
        )

    async def execute(self, input: CapabilityInput[CommerceSession]):
        attempt = await self._service.get_status(
            input.context.tenant_id, input.context.conversation_id
        )
        if attempt is None:
            return CapabilityOutput(
                session=input.session,
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.NOT_FOUND,
                    fragments=(
                        ApprovedResponseFragment(
                            id="payment-status-unavailable",
                            text="No online payment was found for this conversation.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="view-orders",
                        question="Would you like to view recent orders?",
                    ),
                ),
            )
        return CapabilityOutput(session=input.session, outcome=payment_outcome(attempt))

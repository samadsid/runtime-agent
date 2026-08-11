from commerce.models import CommerceSession, OnlinePaymentReady, StockUnavailable
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


class RetryOnlinePaymentCapability(Capability[CommerceSession]):
    def __init__(self, service: PaymentService) -> None:
        self._service = service

    @property
    def metadata(self):
        return CapabilityMetadata(
            name=CapabilityName.RETRY_ONLINE_PAYMENT,
            description="Retries online payment for the current owned provisional order without accepting provider or payment identifiers.",
        )

    async def execute(self, input: CapabilityInput[CommerceSession]):
        try:
            result = await self._service.retry_online_payment(
                input.context.tenant_id, input.context.conversation_id
            )
        except (LookupError, ValueError):
            return CapabilityOutput(
                session=input.session,
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.INVALID_INPUT,
                    fragments=(
                        ApprovedResponseFragment(
                            id="payment-retry-unavailable",
                            text="There is no eligible online payment to retry.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="view-orders",
                        question="Would you like to view your recent orders?",
                    ),
                ),
            )
        if isinstance(result, StockUnavailable):
            return CapabilityOutput(
                session=input.session,
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.CONFLICT,
                    fragments=(
                        ApprovedResponseFragment(
                            id="payment-retry-stock-unavailable",
                            text="Payment cannot be retried because the original quantities are no longer available.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="offer-cash-on-delivery",
                        question="Would you like to check again later?",
                    ),
                ),
            )
        assert isinstance(result, OnlinePaymentReady)
        return CapabilityOutput(
            session=input.session, outcome=payment_outcome(result.attempt)
        )

from __future__ import annotations

from commerce.models import CommerceSession
from commerce.services import OrderService
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


class GetOrderStatusCapability(Capability[CommerceSession]):
    def __init__(self, service: OrderService) -> None:
        self._service = service

    @property
    def metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            name=CapabilityName.GET_ORDER_STATUS,
            description="Returns the latest persisted order status for this conversation.",
        )

    async def execute(
        self, input: CapabilityInput[CommerceSession]
    ) -> CapabilityOutput[CommerceSession]:
        order = await self._service.get_latest_order(input.context.conversation_id)
        if order is None:
            return CapabilityOutput(
                session=input.session,
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.NOT_FOUND,
                    fragments=(
                        ApprovedResponseFragment(
                            id="order-not-found",
                            text="There is no order for this conversation yet.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="start-shopping",
                        question="What product would you like to search for?",
                    ),
                ),
            )

        return CapabilityOutput(
            session=input.session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.SUCCESS,
                fragments=(
                    ApprovedResponseFragment(
                        id="order-status",
                        text=f"Order {order.public_order_number} status: {order.status.value}.",
                    ),
                ),
                protected_values=(order.public_order_number, order.status.value),
            ),
        )

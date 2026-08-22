from __future__ import annotations

from commerce.models import CommerceSession
from commerce.services import CustomerOrderService
from runtime.capabilities import (
    Capability,
    CapabilityInput,
    CapabilityMetadata,
    CapabilityName,
    CapabilityOutput,
)
from runtime.capabilities.order_support import customer_order_status, format_amount
from runtime.contracts import (
    ApprovedResponseFragment,
    ExecutionStatus,
    FollowUpRequest,
    GeneratedExecutionOutcome,
    ResponseFragmentKind,
    ResponseIcon,
    ResponseLayout,
)


class ListOrdersCapability(Capability[CommerceSession]):
    def __init__(self, service: CustomerOrderService) -> None:
        self._service = service

    @property
    def metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            name=CapabilityName.LIST_ORDERS,
            description="Lists recent orders owned by this conversation.",
        )

    async def execute(
        self, input: CapabilityInput[CommerceSession]
    ) -> CapabilityOutput[CommerceSession]:
        limit = input.data.get("limit", 5)
        if (
            not isinstance(limit, int)
            or isinstance(limit, bool)
            or limit < 1
            or limit > 10
        ):
            return CapabilityOutput(
                session=input.session,
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.INVALID_INPUT,
                    fragments=(
                        ApprovedResponseFragment(
                            id="order-limit-invalid",
                            text="The order history limit must be from 1 to 10.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="order-limit-question",
                        question="How many recent orders would you like to see?",
                    ),
                ),
            )

        summaries = await self._service.list_orders(
            input.context.conversation_id, limit
        )
        session = input.session.model_copy(
            update={"recent_order_results": summaries}
        )
        if not summaries:
            return CapabilityOutput(
                session=session,
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.NOT_FOUND,
                    fragments=(
                        ApprovedResponseFragment(
                            id="orders-not-found",
                            text="There are no orders for this conversation yet.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="start-shopping",
                        question="What product would you like to search for?",
                    ),
                ),
            )

        fragments = (
            ApprovedResponseFragment(
                id="recent-orders-heading",
                text="Recent orders",
                kind=ResponseFragmentKind.SECTION,
            ),
            *tuple(
            ApprovedResponseFragment(
                id=f"order-{ordinal}",
                kind=ResponseFragmentKind.ITEM,
                text=(
                    f"{ordinal}. Order {summary.public_order_number}\n"
                    f"   Status: {customer_order_status(summary.status)}\n"
                    f"   Items: {summary.item_count} • Total: {format_amount(summary.total_amount)}\n"
                    f"   Created: {summary.created_at.isoformat()}"
                ),
            )
            for ordinal, summary in enumerate(summaries, start=1)
            ),
        )
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.SUCCESS,
                fragments=fragments,
                follow_up=FollowUpRequest(
                    id="select-recent-order",
                    question="Which order would you like to view?",
                ),
                layout=ResponseLayout.SELECTABLE_LIST,
                heading_emoji=ResponseIcon.ORDER,
                protected_values=tuple(
                    value
                    for summary in summaries
                    for value in (
                        summary.public_order_number,
                        summary.created_at.isoformat(),
                        customer_order_status(summary.status),
                        str(summary.item_count),
                        format_amount(summary.total_amount),
                    )
                ),
            ),
        )

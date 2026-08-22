from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal

from commerce.models import CommerceSession, OrderStatus, PendingOrderCancellation
from commerce.repositories import CustomerCancellationNotAllowedError
from commerce.services import CustomerOrderService
from runtime.capabilities import (
    Capability,
    CapabilityInput,
    CapabilityMetadata,
    CapabilityName,
    CapabilityOutput,
)
from runtime.capabilities.order_support import (
    customer_order_status,
    format_amount,
    resolve_order_target,
    target_error_outcome,
)
from runtime.contracts import (
    ApprovedResponseFragment,
    ExecutionStatus,
    FollowUpRequest,
    GeneratedExecutionOutcome,
    ResponseFragmentKind,
    ResponseIcon,
    ResponseLayout,
)


class CancelOrderCapability(Capability[CommerceSession]):
    def __init__(
        self,
        service: CustomerOrderService,
        support_path: str,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._service = service
        self._support_path = support_path
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @property
    def metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            name=CapabilityName.CANCEL_ORDER,
            description="Reviews and explicitly confirms customer order cancellation.",
        )

    async def execute(
        self, input: CapabilityInput[CommerceSession]
    ) -> CapabilityOutput[CommerceSession]:
        if input.data.get("confirmed") is True:
            return await self._confirm(input)

        session = input.session.model_copy(
            update={"pending_order_cancellation": None}
        )
        try:
            order = await resolve_order_target(
                input.data,
                session,
                self._service,
                input.context.tenant_id,
                input.context.conversation_id,
            )
        except (ValueError, LookupError) as error:
            return CapabilityOutput(
                session=session, outcome=target_error_outcome(error, session)
            )

        if order.status == OrderStatus.CANCELLED:
            return CapabilityOutput(
                session=session,
                outcome=self._cancelled_outcome(order.public_order_number, already=True),
            )
        if order.status != OrderStatus.CONFIRMED:
            return CapabilityOutput(
                session=session,
                outcome=self._denied_outcome(order.public_order_number, order.status),
            )

        total = sum(
            (item.unit_price * item.quantity for item in order.items),
            start=Decimal(0),
        )
        session = session.model_copy(
            update={
                "pending_order_cancellation": PendingOrderCancellation(
                    order_id=order.id, requested_at=self._clock()
                )
            }
        )
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.SUCCESS,
                fragments=(
                    ApprovedResponseFragment(
                        id="cancellation-review",
                        text="Cancellation review",
                        kind=ResponseFragmentKind.SECTION,
                    ),
                    ApprovedResponseFragment(
                        id="cancellation-order",
                        text=f"Order: {order.public_order_number}",
                        kind=ResponseFragmentKind.FIELD,
                    ),
                    ApprovedResponseFragment(
                        id="cancellation-status",
                        text=f"Status: {customer_order_status(order.status)}",
                        kind=ResponseFragmentKind.FIELD,
                    ),
                    ApprovedResponseFragment(
                        id="cancellation-items",
                        text=f"Items: {len(order.items)}",
                        kind=ResponseFragmentKind.FIELD,
                    ),
                    ApprovedResponseFragment(
                        id="cancellation-total",
                        text=f"Total: {format_amount(total)}",
                        kind=ResponseFragmentKind.TOTAL,
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="confirm-order-cancellation",
                    question="Do you explicitly confirm cancelling this order?",
                ),
                protected_values=(
                    order.public_order_number,
                    customer_order_status(order.status),
                    str(len(order.items)),
                    format_amount(total),
                ),
                layout=ResponseLayout.SUMMARY,
                heading_emoji=ResponseIcon.REVIEW,
            ),
        )

    async def _confirm(
        self, input: CapabilityInput[CommerceSession]
    ) -> CapabilityOutput[CommerceSession]:
        pending = input.session.pending_order_cancellation
        if pending is None:
            return CapabilityOutput(
                session=input.session,
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.MISSING_INPUT,
                    fragments=(
                        ApprovedResponseFragment(
                            id="cancellation-not-pending",
                            text="There is no order awaiting cancellation confirmation.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="choose-order-to-cancel",
                        question="Which order would you like to cancel?",
                    ),
                ),
            )

        try:
            current = await self._service.get_order_details(
                input.context.conversation_id, pending.order_id
            )
            already = current.status == OrderStatus.CANCELLED
            order = await self._service.cancel_confirmed_order(
                input.context.conversation_id, pending.order_id
            )
        except CustomerCancellationNotAllowedError as error:
            return CapabilityOutput(
                session=input.session,
                outcome=self._denied_outcome(current.public_order_number, error.status),
            )
        except LookupError as error:
            return CapabilityOutput(
                session=input.session,
                outcome=target_error_outcome(error, input.session),
            )

        session = input.session.model_copy(
            update={"pending_order_cancellation": None}
        )
        return CapabilityOutput(
            session=session,
            outcome=self._cancelled_outcome(order.public_order_number, already=already),
        )

    def _denied_outcome(
        self, order_reference: str, status: OrderStatus
    ) -> GeneratedExecutionOutcome:
        return GeneratedExecutionOutcome(
            status=ExecutionStatus.FAILURE,
            fragments=(
                ApprovedResponseFragment(
                    id="cancellation-denied",
                    text=(
                        f"Order {order_reference} is {customer_order_status(status)}. Self-service cancellation "
                        f"is no longer available. Contact {self._support_path}."
                    ),
                ),
            ),
            protected_values=(order_reference, customer_order_status(status), self._support_path),
        )

    @staticmethod
    def _cancelled_outcome(order_reference: str, *, already: bool) -> GeneratedExecutionOutcome:
        text = (
            f"Order {order_reference} was already Cancelled."
            if already
            else f"Order {order_reference} is Cancelled."
        )
        return GeneratedExecutionOutcome(
            status=ExecutionStatus.SUCCESS,
            fragments=(
                ApprovedResponseFragment(id="order-cancelled", text=text),
            ),
            protected_values=(order_reference, customer_order_status(OrderStatus.CANCELLED)),
        )

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from commerce.models import CommerceSession, Order
from commerce.repositories import OrderNotFoundError
from commerce.services import CustomerOrderService
from runtime.contracts import (
    ApprovedOption,
    ApprovedResponseFragment,
    ExecutionStatus,
    FollowUpRequest,
    GeneratedExecutionOutcome,
)


class MissingOrderTargetError(ValueError):
    pass


class InvalidOrderTargetError(ValueError):
    pass


async def resolve_order_target(
    data: dict[str, object],
    session: CommerceSession,
    service: CustomerOrderService,
    conversation_id: UUID,
) -> Order:
    reference = data.get("order_reference")
    ordinal = data.get("ordinal")
    latest = data.get("latest") is True
    modes = sum((reference is not None, ordinal is not None, latest))
    if modes == 0:
        raise MissingOrderTargetError
    if modes != 1:
        raise InvalidOrderTargetError

    if reference is not None:
        if not isinstance(reference, str):
            raise InvalidOrderTargetError
        try:
            order_id = UUID(reference.strip())
        except (ValueError, AttributeError) as exc:
            raise InvalidOrderTargetError from exc
        return await service.get_order_details(conversation_id, order_id)

    if ordinal is not None:
        if not isinstance(ordinal, int) or isinstance(ordinal, bool):
            raise InvalidOrderTargetError
        index = ordinal - 1
        if index < 0 or index >= len(session.recent_order_results):
            raise InvalidOrderTargetError
        return await service.get_order_details(
            conversation_id, session.recent_order_results[index].order_id
        )

    return await service.get_latest_order(conversation_id)


def target_error_outcome(
    error: Exception, session: CommerceSession
) -> GeneratedExecutionOutcome:
    if isinstance(error, MissingOrderTargetError):
        return GeneratedExecutionOutcome(
            status=ExecutionStatus.MISSING_INPUT,
            fragments=(
                ApprovedResponseFragment(
                    id="order-target-missing",
                    text="Choose an order by reference, recent order number, or latest.",
                ),
            ),
            follow_up=FollowUpRequest(
                id="order-target-question",
                question="Which order would you like to use?",
            ),
        )
    if isinstance(error, InvalidOrderTargetError):
        options = tuple(
            ApprovedOption(
                id=f"recent-order-{ordinal}",
                label=f"{ordinal}. Order {summary.order_id}",
            )
            for ordinal, summary in enumerate(session.recent_order_results, start=1)
        )
        return GeneratedExecutionOutcome(
            status=ExecutionStatus.INVALID_INPUT,
            fragments=(
                ApprovedResponseFragment(
                    id="order-target-invalid",
                    text="That order reference or recent order number is not valid.",
                ),
            ),
            follow_up=FollowUpRequest(
                id="order-target-question",
                question=(
                    "Which recent order would you like to use?"
                    if options
                    else "Please provide an order reference or ask for the latest order."
                ),
                options=options,
            ),
            protected_values=tuple(option.label for option in options),
        )
    if isinstance(error, OrderNotFoundError):
        return GeneratedExecutionOutcome(
            status=ExecutionStatus.NOT_FOUND,
            fragments=(
                ApprovedResponseFragment(
                    id="order-not-found",
                    text="That order was not found.",
                ),
            ),
            follow_up=FollowUpRequest(
                id="view-recent-orders",
                question="Would you like to view your recent orders?",
            ),
        )
    raise error


def format_amount(value: Decimal) -> str:
    return format(value, "f")

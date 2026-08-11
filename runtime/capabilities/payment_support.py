from commerce.models import PaymentAttempt, PaymentAttemptStatus
from runtime.contracts import (
    ApprovedResponseFragment,
    ExecutionStatus,
    FollowUpRequest,
    GeneratedExecutionOutcome,
)


def payment_outcome(attempt: PaymentAttempt) -> GeneratedExecutionOutcome:
    amount = format(attempt.amount, "f")
    protected = [str(attempt.order_id), amount, attempt.currency, attempt.status.value]
    if attempt.status == PaymentAttemptStatus.PENDING:
        if attempt.checkout_url:
            protected.append(attempt.checkout_url)
        protected.append(attempt.expires_at.isoformat())
        return GeneratedExecutionOutcome(
            status=ExecutionStatus.SUCCESS,
            fragments=(
                ApprovedResponseFragment(
                    id="online-payment-ready",
                    text=f"Order {attempt.order_id} is waiting for payment. Amount {amount} {attempt.currency}. Checkout URL: {attempt.checkout_url}. Expires {attempt.expires_at.isoformat()}.",
                ),
            ),
            protected_values=tuple(protected),
        )
    if attempt.status == PaymentAttemptStatus.SUCCEEDED:
        return GeneratedExecutionOutcome(
            status=ExecutionStatus.SUCCESS,
            fragments=(
                ApprovedResponseFragment(
                    id="payment-succeeded",
                    text=f"Payment for order {attempt.order_id} succeeded and the order is confirmed.",
                ),
            ),
            protected_values=tuple(protected),
        )
    if attempt.status in {PaymentAttemptStatus.FAILED, PaymentAttemptStatus.CANCELLED}:
        return GeneratedExecutionOutcome(
            status=ExecutionStatus.FAILURE,
            fragments=(
                ApprovedResponseFragment(
                    id="payment-failed",
                    text=f"Payment for order {attempt.order_id} failed.",
                ),
            ),
            follow_up=FollowUpRequest(
                id="retry-online-payment",
                question="Would you like to retry online payment or switch to cash on delivery?",
            ),
            protected_values=tuple(protected),
        )
    if attempt.status == PaymentAttemptStatus.EXPIRED:
        return GeneratedExecutionOutcome(
            status=ExecutionStatus.FAILURE,
            fragments=(
                ApprovedResponseFragment(
                    id="payment-expired",
                    text=f"Payment for order {attempt.order_id} expired.",
                ),
            ),
            follow_up=FollowUpRequest(
                id="retry-online-payment",
                question="Would you like to retry online payment or switch to cash on delivery?",
            ),
            protected_values=tuple(protected),
        )
    return GeneratedExecutionOutcome(
        status=ExecutionStatus.FAILURE,
        fragments=(
            ApprovedResponseFragment(
                id="payment-temporarily-unavailable",
                text=f"Payment status for order {attempt.order_id} is temporarily unavailable.",
            ),
        ),
        follow_up=FollowUpRequest(
            id="check-payment-status",
            question="Would you like to check the payment status again?",
        ),
        protected_values=tuple(protected),
    )

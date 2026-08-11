from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from commerce.models import (
    AvailableQuantityAccepted,
    CheckoutState,
    CommerceSession,
    RecoveryAvailabilityChanged,
    StaleCheckout,
    StockRecoveryState,
    StockShortage,
    StockUnavailable,
)
from commerce.repositories import CartPersistenceError
from commerce.services import CartService
from runtime.capabilities import (
    Capability,
    CapabilityInput,
    CapabilityMetadata,
    CapabilityName,
    CapabilityOutput,
)
from runtime.capabilities.confirm_order.capability import ConfirmOrderCapability
from runtime.contracts import (
    ApprovedResponseFragment,
    ExecutionStatus,
    FollowUpRequest,
    GeneratedExecutionOutcome,
)


class AcceptAvailableQuantityArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shortage_ordinal: int = Field(strict=True, ge=1)


class AcceptAvailableQuantityCapability(Capability[CommerceSession]):
    def __init__(self, service: CartService) -> None:
        self._service = service

    @property
    def metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            name=CapabilityName.ACCEPT_AVAILABLE_QUANTITY,
            description=(
                "Accepts the currently available quantity for one numbered stock "
                "shortage after an explicit customer choice."
            ),
        )

    async def execute(
        self, input: CapabilityInput[CommerceSession]
    ) -> CapabilityOutput[CommerceSession]:
        recovery = input.session.checkout.stock_recovery
        if recovery is None:
            return self._missing_recovery(input.session)
        try:
            arguments = AcceptAvailableQuantityArguments.model_validate(input.data)
        except ValidationError:
            return self._invalid_ordinal(input.session)
        if arguments.shortage_ordinal > len(recovery.shortages):
            return self._invalid_ordinal(input.session)

        shortage = recovery.shortages[arguments.shortage_ordinal - 1]
        if shortage.available_quantity <= 0:
            return self._availability_changed(input.session, recovery, shortage)
        try:
            result = await self._service.accept_available_quantity(
                input.context.tenant_id,
                input.context.conversation_id,
                recovery.cart_id,
                recovery.cart_version,
                shortage.product_id,
                shortage.available_quantity,
            )
        except CartPersistenceError:
            return self._temporary_failure(input.session)

        if isinstance(result, StaleCheckout):
            return ConfirmOrderCapability._stale_checkout(input.session, result)
        if isinstance(result, RecoveryAvailabilityChanged):
            return self._availability_changed(
                input.session, recovery, result.shortage
            )
        assert isinstance(result, AvailableQuantityAccepted)
        quantity = format(result.quantity, "f")
        session = input.session.model_copy(
            update={
                "cart_items": result.cart.items,
                "checkout": CheckoutState(),
                "pending_saved_profile_use": None,
                "pending_cart_clear": None,
            }
        )
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.SUCCESS,
                fragments=(
                    ApprovedResponseFragment(
                        id="cart-quantity-reduced-to-available",
                        text=(
                            f"Updated {result.product_name} to {quantity} "
                            f"{result.unit}."
                        ),
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="review-checkout-again",
                    question="Would you like to review checkout again?",
                ),
                protected_values=(result.product_name, quantity, result.unit),
            ),
        )

    @staticmethod
    def _availability_changed(
        session: CommerceSession,
        recovery: StockRecoveryState,
        shortage: StockShortage,
    ) -> CapabilityOutput[CommerceSession]:
        shortages = list(recovery.shortages)
        index = next(
            (
                index
                for index, existing in enumerate(shortages)
                if existing.product_id == shortage.product_id
            ),
            None,
        )
        if index is not None:
            shortages[index] = shortage
        output = ConfirmOrderCapability._stock_unavailable(
            session,
            StockUnavailable(
                cart_id=recovery.cart_id,
                cart_version=recovery.cart_version,
                shortages=tuple(shortages),
            ),
        )
        outcome = output.outcome
        assert isinstance(outcome, GeneratedExecutionOutcome)
        fragments = (
            ApprovedResponseFragment(
                id="stock-availability-changed",
                text="Stock changed before the cart quantity could be updated.",
            ),
            *outcome.fragments[1:],
        )
        return output.model_copy(
            update={"outcome": outcome.model_copy(update={"fragments": fragments})}
        )

    @staticmethod
    def _missing_recovery(
        session: CommerceSession,
    ) -> CapabilityOutput[CommerceSession]:
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.CONFLICT,
                fragments=(
                    ApprovedResponseFragment(
                        id="stock-recovery-unavailable",
                        text="There is no current stock-recovery choice to apply.",
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="review-current-cart",
                    question="Would you like to review the current cart?",
                ),
            ),
        )

    @staticmethod
    def _invalid_ordinal(
        session: CommerceSession,
    ) -> CapabilityOutput[CommerceSession]:
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.INVALID_INPUT,
                fragments=(
                    ApprovedResponseFragment(
                        id="invalid-stock-shortage-ordinal",
                        text="That number does not identify a current stock shortage.",
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="choose-stock-shortage",
                    question="Which shortage number would you like to reduce?",
                ),
            ),
        )

    @staticmethod
    def _temporary_failure(
        session: CommerceSession,
    ) -> CapabilityOutput[CommerceSession]:
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.FAILURE,
                fragments=(
                    ApprovedResponseFragment(
                        id="stock-recovery-temporarily-unavailable",
                        text="The cart could not be updated safely right now.",
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="retry-stock-recovery",
                    question="Would you like to try again?",
                ),
            ),
        )

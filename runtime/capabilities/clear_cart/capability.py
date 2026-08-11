from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from commerce.models import (
    Cart,
    CheckoutState,
    CommerceSession,
    PendingCartClear,
)
from commerce.repositories import (
    CartNotFoundError,
    CartPersistenceError,
    StaleCartError,
)
from commerce.services import CartService
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
    ResponseFragmentKind,
)


class ClearCartArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmed: bool = Field(default=False, strict=True)
    declined: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def validate_single_decision(self) -> ClearCartArguments:
        if self.confirmed and self.declined:
            raise ValueError("Clear confirmation and decline are mutually exclusive.")
        return self


class ClearCartCapability(Capability[CommerceSession]):
    def __init__(
        self,
        service: CartService,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._service = service
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @property
    def metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            name=CapabilityName.CLEAR_CART,
            description=(
                "Reviews and explicitly confirms clearing the complete active cart. "
                "Use confirmed=false for the first request, confirmed=true only for "
                "explicit confirmation, or declined=true for an explicit decline."
            ),
        )

    async def execute(
        self, input: CapabilityInput[CommerceSession]
    ) -> CapabilityOutput[CommerceSession]:
        try:
            arguments = ClearCartArguments.model_validate(input.data)
        except ValidationError:
            return self._invalid_decision(input.session)
        if arguments.declined:
            return self._decline(input.session)
        if arguments.confirmed:
            return await self._confirm(input)
        return await self._review(input)

    async def _review(
        self, input: CapabilityInput[CommerceSession]
    ) -> CapabilityOutput[CommerceSession]:
        try:
            cart = await self._service.get_active(
                input.context.tenant_id, input.context.conversation_id
            )
        except CartPersistenceError:
            return self._persistence_failure(input.session)
        if cart is None or not cart.items:
            session = input.session.model_copy(
                update={"cart_items": (), "pending_cart_clear": None}
            )
            return self._empty_cart(session)
        session = self._session_for_review(input.session, cart)
        return CapabilityOutput(session=session, outcome=self._review_outcome(cart))

    async def _confirm(
        self, input: CapabilityInput[CommerceSession]
    ) -> CapabilityOutput[CommerceSession]:
        pending = input.session.pending_cart_clear
        if pending is None:
            return self._missing_confirmation(input.session)
        try:
            cart = await self._service.clear_cart(
                input.context.tenant_id,
                input.context.conversation_id,
                pending.cart_id,
                pending.cart_version,
            )
        except StaleCartError:
            return await self._refresh_stale_review(input)
        except CartNotFoundError:
            try:
                current = await self._service.get_active(
                    input.context.tenant_id, input.context.conversation_id
                )
            except CartPersistenceError:
                return self._persistence_failure(
                    input.session.model_copy(update={"pending_cart_clear": None})
                )
            if current is not None and current.items:
                session = self._session_for_review(input.session, current)
                return CapabilityOutput(
                    session=session,
                    outcome=self._review_outcome(current, stale=True),
                )
            session = input.session.model_copy(
                update={"cart_items": (), "pending_cart_clear": None}
            )
            return self._empty_cart(session)
        except CartPersistenceError:
            return self._persistence_failure(input.session)

        session = input.session.model_copy(
            update={
                "cart_items": cart.items,
                "pending_cart_clear": None,
                "checkout": CheckoutState(),
                "pending_saved_profile_use": None,
            }
        )
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.SUCCESS,
                fragments=(
                    ApprovedResponseFragment(
                        id="cart-cleared",
                        text="Your cart has been cleared.",
                    ),
                ),
            ),
        )

    async def _refresh_stale_review(
        self, input: CapabilityInput[CommerceSession]
    ) -> CapabilityOutput[CommerceSession]:
        try:
            current = await self._service.get_active(
                input.context.tenant_id, input.context.conversation_id
            )
        except CartPersistenceError:
            return self._persistence_failure(
                input.session.model_copy(update={"pending_cart_clear": None})
            )
        if current is None or not current.items:
            session = input.session.model_copy(
                update={"cart_items": (), "pending_cart_clear": None}
            )
            return self._empty_cart(session)
        session = self._session_for_review(input.session, current)
        return CapabilityOutput(
            session=session,
            outcome=self._review_outcome(current, stale=True),
        )

    def _session_for_review(
        self, session: CommerceSession, cart: Cart
    ) -> CommerceSession:
        return session.model_copy(
            update={
                "cart_items": cart.items,
                "pending_cart_clear": PendingCartClear(
                    cart_id=cart.id,
                    cart_version=cart.version,
                    requested_at=self._clock(),
                ),
            }
        )

    @staticmethod
    def _review_outcome(
        cart: Cart, *, stale: bool = False
    ) -> GeneratedExecutionOutcome:
        fragments: list[ApprovedResponseFragment] = []
        if stale:
            fragments.append(
                ApprovedResponseFragment(
                    id="stale-cart-clear",
                    text="Your cart changed after the previous review. Nothing was cleared.",
                )
            )
        fragments.append(
            ApprovedResponseFragment(
                id="clear-cart-heading",
                text="Review the cart items to clear:",
            )
        )
        fragments.extend(
            ApprovedResponseFragment(
                id=f"clear-cart-item-{ordinal}",
                text=(
                    f"{ordinal}. {item.product.name} — "
                    f"{format(item.quantity, 'f')} {item.product.unit}"
                ),
                kind=ResponseFragmentKind.ITEM,
            )
            for ordinal, item in enumerate(cart.items, start=1)
        )
        return GeneratedExecutionOutcome(
            status=ExecutionStatus.SUCCESS,
            fragments=tuple(fragments),
            follow_up=FollowUpRequest(
                id="confirm-clear-cart",
                question="Do you explicitly confirm clearing this entire cart?",
            ),
            protected_values=tuple(
                value
                for ordinal, item in enumerate(cart.items, start=1)
                for value in (
                    str(ordinal),
                    item.product.name,
                    format(item.quantity, "f"),
                    item.product.unit,
                )
            ),
        )

    @staticmethod
    def _decline(session: CommerceSession) -> CapabilityOutput[CommerceSession]:
        if session.pending_cart_clear is None:
            return ClearCartCapability._missing_confirmation(session)
        return CapabilityOutput(
            session=session.model_copy(update={"pending_cart_clear": None}),
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.SUCCESS,
                fragments=(
                    ApprovedResponseFragment(
                        id="cart-clear-declined",
                        text="Your cart was not cleared.",
                    ),
                ),
            ),
        )

    @staticmethod
    def _empty_cart(session: CommerceSession) -> CapabilityOutput[CommerceSession]:
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.NOT_FOUND,
                fragments=(
                    ApprovedResponseFragment(id="empty-cart", text="Your cart is empty."),
                ),
                follow_up=FollowUpRequest(
                    id="search-product-for-empty-cart",
                    question="What product would you like to search for?",
                ),
            ),
        )

    @staticmethod
    def _missing_confirmation(
        session: CommerceSession,
    ) -> CapabilityOutput[CommerceSession]:
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.MISSING_INPUT,
                fragments=(
                    ApprovedResponseFragment(
                        id="cart-clear-not-pending",
                        text="There is no reviewed cart awaiting clear confirmation.",
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="request-clear-cart-review",
                    question="Would you like to review your current cart before clearing it?",
                ),
            ),
        )

    @staticmethod
    def _invalid_decision(
        session: CommerceSession,
    ) -> CapabilityOutput[CommerceSession]:
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.INVALID_INPUT,
                fragments=(
                    ApprovedResponseFragment(
                        id="invalid-cart-clear-decision",
                        text="The cart-clear decision was invalid.",
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="request-cart-clear-decision",
                    question="Do you want to confirm or decline clearing the reviewed cart?",
                ),
            ),
        )

    @staticmethod
    def _persistence_failure(
        session: CommerceSession,
    ) -> CapabilityOutput[CommerceSession]:
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.FAILURE,
                fragments=(
                    ApprovedResponseFragment(
                        id="cart-clear-persistence-failed",
                        text="The cart could not be cleared. Its items were not changed.",
                    ),
                ),
            ),
        )

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from commerce.models import CheckoutState, CommerceSession
from commerce.repositories import (
    CartItemOrdinalError,
    CartNotFoundError,
    CartPersistenceError,
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
    ApprovedOption,
    ApprovedResponseFragment,
    ExecutionStatus,
    FollowUpRequest,
    GeneratedExecutionOutcome,
)


class UpdateCartItemQuantityArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ordinal: int = Field(strict=True, ge=1)
    quantity: Decimal = Field(gt=0, allow_inf_nan=False)


class UpdateCartItemQuantityCapability(Capability[CommerceSession]):
    def __init__(self, service: CartService) -> None:
        self._service = service

    @property
    def metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            name=CapabilityName.UPDATE_CART_ITEM_QUANTITY,
            description=(
                "Replaces one persisted cart item's quantity using its 1-based "
                "cart ordinal. Requires strict integer 'ordinal' and positive "
                "decimal 'quantity' arguments."
            ),
        )

    async def execute(
        self, input: CapabilityInput[CommerceSession]
    ) -> CapabilityOutput[CommerceSession]:
        try:
            current = await self._service.get_active(
                input.context.tenant_id, input.context.conversation_id
            )
        except CartPersistenceError:
            return self._persistence_failure(input.session)
        session_updates: dict[str, object] = {
            "cart_items": current.items if current is not None else ()
        }
        pending = input.session.pending_cart_clear
        if current is None or (
            pending is not None
            and (
                pending.cart_id != current.id
                or pending.cart_version != current.version
            )
        ):
            session_updates["pending_cart_clear"] = None
        session = input.session.model_copy(update=session_updates)
        if current is None or not current.items:
            return self._empty_cart(session)

        if "ordinal" not in input.data:
            return self._invalid_ordinal(session, ExecutionStatus.MISSING_INPUT)
        if "quantity" not in input.data:
            return self._invalid_quantity(session, ExecutionStatus.MISSING_INPUT)
        try:
            arguments = UpdateCartItemQuantityArguments.model_validate(input.data)
        except ValidationError:
            if not self._valid_ordinal(input.data.get("ordinal"), len(current.items)):
                return self._invalid_ordinal(session, ExecutionStatus.INVALID_INPUT)
            return self._invalid_quantity(session, ExecutionStatus.INVALID_INPUT)

        if arguments.ordinal > len(current.items):
            return self._invalid_ordinal(session, ExecutionStatus.INVALID_INPUT)
        item = current.items[arguments.ordinal - 1]
        try:
            updated = await self._service.update_item_quantity(
                input.context.tenant_id,
                input.context.conversation_id,
                arguments.ordinal,
                arguments.quantity,
            )
        except CartItemOrdinalError:
            try:
                refreshed = await self._service.get_active(
                    input.context.tenant_id, input.context.conversation_id
                )
            except CartPersistenceError:
                return self._persistence_failure(session)
            session = session.model_copy(
                update={"cart_items": refreshed.items if refreshed is not None else ()}
            )
            return self._invalid_ordinal(session, ExecutionStatus.INVALID_INPUT)
        except CartNotFoundError:
            return self._empty_cart(
                session.model_copy(update={"cart_items": (), "pending_cart_clear": None})
            )
        except CartPersistenceError:
            return self._persistence_failure(session)

        updates: dict[str, object] = {"cart_items": updated.items}
        if updated.version != current.version:
            updates.update(
                checkout=CheckoutState(),
                pending_cart_clear=None,
            )
        session = session.model_copy(update=updates)
        quantity = format(arguments.quantity, "f")
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.SUCCESS,
                fragments=(
                    ApprovedResponseFragment(
                        id="cart-item-quantity-updated",
                        text=(
                            f"Updated {item.product.name} to {quantity} "
                            f"{item.product.unit}."
                        ),
                    ),
                ),
                protected_values=(item.product.name, quantity, item.product.unit),
            ),
        )

    @staticmethod
    def _valid_ordinal(value: object, item_count: int) -> bool:
        return type(value) is int and 1 <= value <= item_count

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
    def _invalid_ordinal(
        session: CommerceSession, status: ExecutionStatus
    ) -> CapabilityOutput[CommerceSession]:
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=status,
                fragments=(
                    ApprovedResponseFragment(
                        id="invalid-cart-update-ordinal",
                        text="That reference does not identify one cart item.",
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="choose-cart-item-to-update",
                    question="Which cart item number would you like to update?",
                    options=tuple(
                        ApprovedOption(
                            id=f"cart-item-{ordinal}",
                            label=f"{ordinal}. {item.product.name}",
                        )
                        for ordinal, item in enumerate(session.cart_items, start=1)
                    ),
                ),
                protected_values=tuple(
                    value
                    for ordinal, item in enumerate(session.cart_items, start=1)
                    for value in (str(ordinal), item.product.name)
                ),
            ),
        )

    @staticmethod
    def _invalid_quantity(
        session: CommerceSession, status: ExecutionStatus
    ) -> CapabilityOutput[CommerceSession]:
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=status,
                fragments=(
                    ApprovedResponseFragment(
                        id="invalid-cart-update-quantity",
                        text="The new quantity must be a finite number greater than zero.",
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="request-cart-update-quantity",
                    question="What positive quantity should this cart item have?",
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
                        id="cart-update-persistence-failed",
                        text="The cart quantity could not be saved. Your cart was not changed.",
                    ),
                ),
            ),
        )

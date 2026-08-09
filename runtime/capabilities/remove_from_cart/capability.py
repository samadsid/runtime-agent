from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError

from commerce.models import CommerceSession
from commerce.repositories import InvalidCartOrdinalError
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


class RemoveFromCartArguments(BaseModel):
    ordinal: int = Field(strict=True, ge=1)


class RemoveFromCartCapability(Capability[CommerceSession]):
    def __init__(self, service: CartService) -> None:
        self._service = service

    @property
    def metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            name=CapabilityName.REMOVE_FROM_CART,
            description=(
                "Removes an item from the persisted cart using its 1-based cart "
                "ordinal. Requires an integer 'ordinal' argument."
            ),
        )

    async def execute(
        self, input: CapabilityInput[CommerceSession]
    ) -> CapabilityOutput[CommerceSession]:
        cart = await self._service.get_active(
            input.context.tenant_id, input.context.conversation_id
        )
        session = input.session.model_copy(
            update={"cart_items": cart.items if cart is not None else ()}
        )
        if cart is None or not cart.items:
            return self._empty_cart(session)

        if "ordinal" not in input.data:
            return self._invalid_ordinal(session, ExecutionStatus.MISSING_INPUT)
        try:
            arguments = RemoveFromCartArguments.model_validate(input.data)
        except ValidationError:
            return self._invalid_ordinal(session, ExecutionStatus.INVALID_INPUT)

        index = arguments.ordinal - 1
        if index >= len(cart.items):
            return self._invalid_ordinal(session, ExecutionStatus.INVALID_INPUT)

        item = cart.items[index]
        try:
            updated_cart = await self._service.remove_by_ordinal(
                cart.id, arguments.ordinal
            )
        except InvalidCartOrdinalError:
            current = await self._service.get_active(
                input.context.tenant_id, input.context.conversation_id
            )
            session = session.model_copy(
                update={"cart_items": current.items if current is not None else ()}
            )
            return self._invalid_ordinal(session, ExecutionStatus.INVALID_INPUT)

        session = session.model_copy(update={"cart_items": updated_cart.items})
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.SUCCESS,
                fragments=(
                    ApprovedResponseFragment(
                        id="cart-item-removed",
                        text=(
                            f"Removed {format(item.quantity, 'f')} "
                            f"{item.product.unit} {item.product.name} from your cart."
                        ),
                    ),
                ),
                protected_values=(
                    format(item.quantity, "f"),
                    item.product.unit,
                    item.product.name,
                ),
            ),
        )

    @staticmethod
    def _empty_cart(session: CommerceSession) -> CapabilityOutput[CommerceSession]:
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.NOT_FOUND,
                fragments=(ApprovedResponseFragment(id="empty-cart", text="Your cart is empty."),),
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
                        id="invalid-cart-ordinal",
                        text="That number does not match an item in your cart.",
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="request-cart-ordinal",
                    question="Which cart item number would you like to remove?",
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

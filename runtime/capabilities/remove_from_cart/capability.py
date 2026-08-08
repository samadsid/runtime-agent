from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError

from commerce.models import CommerceSession
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
                "Removes an item from the current cart using its 1-based cart "
                "ordinal. Requires an integer 'ordinal' argument."
            ),
        )

    async def execute(
        self,
        input: CapabilityInput[CommerceSession],
    ) -> CapabilityOutput[CommerceSession]:
        if not input.session.cart_items:
            return self._empty_cart(input.session)

        if "ordinal" not in input.data:
            return self._invalid_ordinal(
                input.session,
                ExecutionStatus.MISSING_INPUT,
            )

        try:
            arguments = RemoveFromCartArguments.model_validate(input.data)
        except ValidationError:
            return self._invalid_ordinal(
                input.session,
                ExecutionStatus.INVALID_INPUT,
            )

        index = arguments.ordinal - 1
        if index >= len(input.session.cart_items):
            return self._invalid_ordinal(
                input.session,
                ExecutionStatus.INVALID_INPUT,
            )

        item = input.session.cart_items[index]
        session = self._service.remove(input.session, index)
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
            ),
        )

    @staticmethod
    def _empty_cart(
        session: CommerceSession,
    ) -> CapabilityOutput[CommerceSession]:
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.NOT_FOUND,
                fragments=(
                    ApprovedResponseFragment(
                        id="empty-cart",
                        text="Your cart is empty.",
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="search-product-for-empty-cart",
                    question="What product would you like to search for?",
                ),
            ),
        )

    @staticmethod
    def _invalid_ordinal(
        session: CommerceSession,
        status: ExecutionStatus,
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
                        for ordinal, item in enumerate(
                            session.cart_items,
                            start=1,
                        )
                    ),
                ),
            ),
        )

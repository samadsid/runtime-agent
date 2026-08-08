from __future__ import annotations

from commerce.models import CommerceSession
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


class ViewCartCapability(Capability[CommerceSession]):
    @property
    def metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            name=CapabilityName.VIEW_CART,
            description="Shows the customer's current session cart.",
        )

    async def execute(
        self,
        input: CapabilityInput[CommerceSession],
    ) -> CapabilityOutput[CommerceSession]:
        if not input.session.cart_items:
            return CapabilityOutput(
                session=input.session,
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

        fragments = [
            ApprovedResponseFragment(
                id="cart-heading",
                text="Your cart:",
            )
        ]
        fragments.extend(
            ApprovedResponseFragment(
                id=f"cart-item-{ordinal}",
                text=(
                    f"{ordinal}. {item.product.name} — "
                    f"{format(item.quantity, 'f')} {item.product.unit}"
                ),
                kind=ResponseFragmentKind.ITEM,
            )
            for ordinal, item in enumerate(input.session.cart_items, start=1)
        )
        return CapabilityOutput(
            session=input.session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.SUCCESS,
                fragments=tuple(fragments),
            ),
        )

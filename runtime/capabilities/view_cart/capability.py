from __future__ import annotations

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
    ApprovedResponseFragment,
    ExecutionStatus,
    FollowUpRequest,
    GeneratedExecutionOutcome,
    ResponseFragmentKind,
)


class ViewCartCapability(Capability[CommerceSession]):
    def __init__(self, service: CartService) -> None:
        self._service = service

    @property
    def metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            name=CapabilityName.VIEW_CART,
            description="Shows the customer's persisted active cart.",
        )

    async def execute(
        self, input: CapabilityInput[CommerceSession]
    ) -> CapabilityOutput[CommerceSession]:
        cart = await self._service.get_active(
            input.context.tenant_id, input.context.conversation_id
        )
        items = cart.items if cart is not None else ()
        session = input.session.model_copy(update={"cart_items": items})
        if not items:
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

        fragments = [ApprovedResponseFragment(id="cart-heading", text="Your cart:")]
        fragments.extend(
            ApprovedResponseFragment(
                id=f"cart-item-{ordinal}",
                text=(
                    f"{ordinal}. {item.product.name} — "
                    f"{format(item.quantity, 'f')} {item.product.unit}"
                ),
                kind=ResponseFragmentKind.ITEM,
            )
            for ordinal, item in enumerate(items, start=1)
        )
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.SUCCESS,
                fragments=tuple(fragments),
                protected_values=tuple(
                    value
                    for ordinal, item in enumerate(items, start=1)
                    for value in (
                        str(ordinal),
                        item.product.name,
                        format(item.quantity, "f"),
                        item.product.unit,
                    )
                ),
            ),
        )

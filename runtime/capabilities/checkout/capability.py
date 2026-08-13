from __future__ import annotations

from commerce.models import CheckoutStage, CheckoutState, CommerceSession
from commerce.services import CartService
from runtime.capabilities import (
    Capability,
    CapabilityInput,
    CapabilityMetadata,
    CapabilityName,
    CapabilityOutput,
)
from runtime.capabilities.checkout_support import (
    all_delivery_details_outcome,
    confirmation_review_outcome,
    missing_detail_outcome,
)
from runtime.contracts import (
    ApprovedResponseFragment,
    ExecutionStatus,
    FollowUpRequest,
    GeneratedExecutionOutcome,
    ResponseFragmentKind,
)


class CheckoutCapability(Capability[CommerceSession]):
    def __init__(self, service: CartService) -> None:
        self._service = service

    @property
    def metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            name=CapabilityName.CHECKOUT,
            description=(
                "Starts checkout for the persisted cart or advances a reviewed "
                "cart after the customer explicitly asks to proceed."
            ),
        )

    async def execute(
        self, input: CapabilityInput[CommerceSession]
    ) -> CapabilityOutput[CommerceSession]:
        cart = await self._service.get_active(
            input.context.tenant_id, input.context.conversation_id
        )
        if cart is None or not cart.items:
            session = input.session.model_copy(
                update={
                    "cart_items": (),
                    "checkout": CheckoutState(),
                    "pending_saved_profile_use": None,
                    "pending_cart_clear": None,
                    "pending_cart_addition": None,
                }
            )
            return CapabilityOutput(
                session=session,
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.NOT_FOUND,
                    fragments=(
                        ApprovedResponseFragment(
                            id="checkout-empty-cart", text="Your cart is empty."
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="search-product-for-checkout",
                        question="What product would you like to search for?",
                    ),
                ),
            )

        session_updates: dict[str, object] = {
            "cart_items": cart.items,
            "pending_cart_addition": None,
        }
        pending = input.session.pending_cart_clear
        if pending is not None and (
            pending.cart_id != cart.id or pending.cart_version != cart.version
        ):
            session_updates["pending_cart_clear"] = None
        session = input.session.model_copy(update=session_updates)
        checkout = session.checkout
        if (
            checkout.source_cart_id == cart.id
            and checkout.source_cart_version == cart.version
            and checkout.stage == CheckoutStage.REVIEWING_CART
        ):
            checkout = checkout.model_copy(
                update={"stage": CheckoutStage.COLLECTING_DETAILS}
            )
            session = session.model_copy(update={"checkout": checkout})
            return CapabilityOutput(
                session=session,
                outcome=all_delivery_details_outcome(
                    saved_addresses_available=(
                        input.context.channel_customer_id is not None
                    )
                ),
            )

        if (
            checkout.source_cart_id == cart.id
            and checkout.source_cart_version == cart.version
            and checkout.stage == CheckoutStage.COLLECTING_DETAILS
        ):
            return CapabilityOutput(
                session=session,
                outcome=missing_detail_outcome(checkout),
            )

        if (
            checkout.source_cart_id == cart.id
            and checkout.source_cart_version == cart.version
            and checkout.stage == CheckoutStage.READY_TO_CONFIRM
        ):
            return CapabilityOutput(
                session=session,
                outcome=confirmation_review_outcome(checkout),
            )

        checkout = CheckoutState(
            stage=CheckoutStage.REVIEWING_CART,
            source_cart_id=cart.id,
            source_cart_version=cart.version,
            payment_method=None,
        )
        session = session.model_copy(update={"checkout": checkout})
        fragments = [
            ApprovedResponseFragment(
                id="checkout-cart-heading", text="Checkout cart review:"
            )
        ]
        fragments.extend(
            ApprovedResponseFragment(
                id=f"checkout-item-{ordinal}",
                text=(
                    f"{ordinal}. {item.product.name} — "
                    f"{format(item.quantity, 'f')} {item.product.unit} at "
                    f"₹{item.product.price}/{item.product.unit}"
                ),
                kind=ResponseFragmentKind.ITEM,
            )
            for ordinal, item in enumerate(cart.items, start=1)
        )
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.SUCCESS,
                fragments=tuple(fragments),
                follow_up=FollowUpRequest(
                    id="proceed-with-checkout",
                    question="Would you like to proceed with checkout?",
                ),
                protected_values=tuple(
                    value
                    for ordinal, item in enumerate(cart.items, start=1)
                    for value in (
                        str(ordinal),
                        item.product.name,
                        format(item.quantity, "f"),
                        item.product.unit,
                        f"₹{item.product.price}",
                    )
                ),
            ),
        )

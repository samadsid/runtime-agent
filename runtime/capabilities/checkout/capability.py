from __future__ import annotations

from commerce.models import (
    CheckoutStage,
    CheckoutState,
    CommerceSession,
    PendingSavedProfileUse,
    SavedAddressOption,
)
from commerce.services import CartService, SavedDeliveryDetailsService
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
    def __init__(
        self,
        service: CartService,
        saved_details_service: SavedDeliveryDetailsService | None = None,
    ) -> None:
        self._service = service
        self._saved_details_service = saved_details_service

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
            saved_offer = await self._saved_details_offer(input, session)
            if saved_offer is not None:
                return saved_offer
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

    async def _saved_details_offer(
        self,
        input: CapabilityInput[CommerceSession],
        session: CommerceSession,
    ) -> CapabilityOutput[CommerceSession] | None:
        if (
            self._saved_details_service is None
            or input.context.channel_customer_id is None
        ):
            return None
        profile, addresses = await self._saved_details_service.list_addresses(
            input.context.tenant_id,
            input.context.channel,
            input.context.channel_customer_id,
        )
        if profile is None or not addresses:
            return None
        address = next((item for item in addresses if item.is_default), addresses[0])
        option = SavedAddressOption(
            address_id=address.id,
            label=address.label,
            delivery_address=address.delivery_address,
            is_default=address.is_default,
            version=address.version,
        )
        pending = PendingSavedProfileUse(
            profile_id=profile.id,
            customer_name=profile.customer_name,
            phone_number=profile.phone_number,
            address_id=address.id,
            delivery_address=address.delivery_address,
        )
        fragments = [
            ApprovedResponseFragment(
                id="saved-checkout-details-available",
                text="Saved delivery details are available:",
            )
        ]
        protected = [address.label, address.delivery_address]
        if profile.customer_name is not None:
            fragments.append(
                ApprovedResponseFragment(
                    id="saved-checkout-name",
                    text=f"Name: {profile.customer_name}",
                )
            )
            protected.append(profile.customer_name)
        if profile.phone_number is not None:
            masked_phone = self._mask_phone(profile.phone_number)
            fragments.append(
                ApprovedResponseFragment(
                    id="saved-checkout-phone",
                    text=f"Phone: {masked_phone}",
                )
            )
            protected.append(masked_phone)
        fragments.append(
            ApprovedResponseFragment(
                id="saved-checkout-address",
                text=f"Address ({address.label}): {address.delivery_address}",
            )
        )
        return CapabilityOutput(
            session=session.model_copy(
                update={
                    "recent_saved_addresses": (option,),
                    "pending_saved_profile_use": pending,
                }
            ),
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.MISSING_INPUT,
                fragments=tuple(fragments),
                follow_up=FollowUpRequest(
                    id="confirm-saved-checkout-details",
                    question=(
                        "Would you like to use these saved delivery details, "
                        "or provide different ones?"
                    ),
                ),
                protected_values=tuple(protected),
            ),
        )

    @staticmethod
    def _mask_phone(phone: str) -> str:
        return f"{'*' * max(0, len(phone) - 4)}{phone[-4:]}"

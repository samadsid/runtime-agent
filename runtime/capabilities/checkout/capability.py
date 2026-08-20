from __future__ import annotations

from decimal import Decimal

from commerce.models import (
    ChannelName,
    CheckoutStage,
    CheckoutState,
    CommerceSession,
    PendingSavedProfileUse,
    SavedAddressOption,
    ServiceabilityKind,
)
from commerce.services import (
    CartService,
    DeliveryService,
    PaymentMethodPolicy,
    SavedDeliveryDetailsService,
)
from runtime.capabilities import (
    Capability,
    CapabilityInput,
    CapabilityMetadata,
    CapabilityName,
    CapabilityOutput,
)
from runtime.capabilities.checkout_support import (
    advance_to_payment,
    all_delivery_details_outcome,
    confirmation_review_outcome,
    format_money,
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
        payment_policy: PaymentMethodPolicy | None = None,
        delivery_service: DeliveryService | None = None,
        require_whatsapp_location: bool = False,
    ) -> None:
        self._service = service
        self._saved_details_service = saved_details_service
        self._payment_policy = payment_policy
        self._delivery_service = delivery_service
        self._require_whatsapp_location = require_whatsapp_location

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
            if self._location_required(input):
                return CapabilityOutput(
                    session=session, outcome=self._location_outcome()
                )
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
            if self._location_required(input) and checkout.delivery_location is None:
                return CapabilityOutput(
                    session=session, outcome=self._location_outcome()
                )
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
                outcome=confirmation_review_outcome(checkout, cart.items),
            )

        if (
            checkout.source_cart_id == cart.id
            and checkout.source_cart_version == cart.version
            and checkout.stage == CheckoutStage.SELECTING_PAYMENT_METHOD
            and self._payment_policy is not None
        ):
            checkout, outcome = await advance_to_payment(
                checkout, cart.items, input.context.tenant_id, self._payment_policy
            )
            return CapabilityOutput(
                session=session.model_copy(update={"checkout": checkout}),
                outcome=outcome,
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
                id="checkout-cart-summary",
                text="🛒 Cart Summary",
                kind=ResponseFragmentKind.SECTION,
            )
        ]
        total = sum(
            (item.quantity * item.product.price for item in cart.items),
            start=Decimal(0),
        )
        currencies = {item.product.currency for item in cart.items}
        if len(currencies) != 1:
            raise ValueError("Checkout cart requires one currency.")
        currency = next(iter(currencies), "INR")
        for ordinal, item in enumerate(cart.items, start=1):
            line_total = item.quantity * item.product.price
            fragments.append(
                ApprovedResponseFragment(
                    id=f"checkout-item-{ordinal}",
                    text=(
                        f"{ordinal}. {item.product.name}\n"
                        f"{format(item.quantity, 'f')} {item.product.unit} × "
                        f"{format_money(item.product.price, currency)}/{item.product.unit} = "
                        f"{format_money(line_total, currency)}"
                    ),
                    kind=ResponseFragmentKind.ITEM,
                )
            )
        fragments.append(
            ApprovedResponseFragment(
                id="checkout-cart-total",
                text=f"Total: {format_money(total, currency)}",
                kind=ResponseFragmentKind.TOTAL,
            )
        )
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.SUCCESS,
                fragments=tuple(fragments),
                follow_up=FollowUpRequest(
                    id="proceed-from-cart-review",
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
                        format_money(item.product.price, currency),
                        format_money(item.quantity * item.product.price, currency),
                    )
                )
                + (format_money(total, currency),),
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
        checked_location = address.delivery_location
        if self._location_required(input):
            if checked_location is None:
                return CapabilityOutput(
                    session=session,
                    outcome=GeneratedExecutionOutcome(
                        status=ExecutionStatus.MISSING_INPUT,
                        fragments=(
                            ApprovedResponseFragment(
                                id="saved-location-no-longer-serviceable",
                                text="The saved text address needs an exact current delivery-location check.",
                            ),
                        ),
                        follow_up=FollowUpRequest(
                            id="share-delivery-location",
                            question="Please send the destination using the WhatsApp Location attachment.",
                        ),
                    ),
                )
            assert self._delivery_service is not None
            serviceability = await self._delivery_service.check_serviceability(
                input.context.tenant_id,
                checked_location.latitude,
                checked_location.longitude,
            )
            if serviceability.kind is ServiceabilityKind.TEMPORARILY_UNAVAILABLE:
                return CapabilityOutput(
                    session=session,
                    outcome=GeneratedExecutionOutcome(
                        status=ExecutionStatus.FAILURE,
                        fragments=(
                            ApprovedResponseFragment(
                                id="delivery-serviceability-temporarily-unavailable",
                                text="The saved delivery location could not be checked temporarily; it was not rejected.",
                            ),
                        ),
                        follow_up=FollowUpRequest(
                            id="retry-saved-location",
                            question="Would you like to retry the saved location check?",
                        ),
                    ),
                )
            if serviceability.kind is ServiceabilityKind.OUTSIDE_SERVICE_AREA:
                return CapabilityOutput(
                    session=session,
                    outcome=GeneratedExecutionOutcome(
                        status=ExecutionStatus.CONFLICT,
                        fragments=(
                            ApprovedResponseFragment(
                                id="saved-location-no-longer-serviceable",
                                text="The saved delivery location is no longer in the active delivery area.",
                            ),
                        ),
                        follow_up=FollowUpRequest(
                            id="share-another-delivery-location",
                            question="Please share another delivery location.",
                        ),
                    ),
                )
            assert (
                serviceability.zone_id
                and serviceability.zone_name
                and serviceability.zone_version
            )
            checked_location = checked_location.model_copy(
                update={
                    "zone_id": serviceability.zone_id,
                    "zone_name": serviceability.zone_name,
                    "zone_version": serviceability.zone_version,
                    "checked_at": serviceability.checked_at,
                }
            )
        option = SavedAddressOption(
            address_id=address.id,
            label=address.label,
            delivery_address=address.delivery_address,
            delivery_location=checked_location,
            is_default=address.is_default,
            version=address.version,
            serviceability_status=address.serviceability_status,
        )
        pending = PendingSavedProfileUse(
            profile_id=profile.id,
            customer_name=profile.customer_name,
            phone_number=profile.phone_number,
            address_id=address.id,
            delivery_address=address.delivery_address,
            delivery_location=checked_location,
        )
        fragments = [
            ApprovedResponseFragment(
                id="saved-delivery-details",
                text="Saved Delivery Details",
                kind=ResponseFragmentKind.SECTION,
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
                    id="use-saved-delivery-details",
                    question="Would you like to use these saved delivery details?",
                ),
                protected_values=tuple(protected),
            ),
        )

    def _location_required(self, input: CapabilityInput[CommerceSession]) -> bool:
        return (
            self._require_whatsapp_location
            and input.context.channel is ChannelName.WHATSAPP
            and self._delivery_service is not None
        )

    @staticmethod
    def _location_outcome() -> GeneratedExecutionOutcome:
        return GeneratedExecutionOutcome(
            status=ExecutionStatus.MISSING_INPUT,
            fragments=(
                ApprovedResponseFragment(
                    id="delivery-location-requested",
                    text="An exact delivery-location check is required for WhatsApp checkout.",
                ),
            ),
            follow_up=FollowUpRequest(
                id="share-delivery-location",
                question="Please send the delivery destination using the WhatsApp Location attachment, or say if sharing is unavailable.",
            ),
        )

    @staticmethod
    def _mask_phone(phone: str) -> str:
        stripped = phone.strip()
        return f"{'*' * max(0, len(stripped) - 4)}{stripped[-4:]}"

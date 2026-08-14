from __future__ import annotations

from decimal import Decimal

from commerce.models import (
    CheckoutStage,
    CheckoutState,
    CommerceSession,
    DirectCartResult,
    DirectCartResultKind,
)
from runtime.capabilities import CapabilityOutput
from runtime.contracts import (
    ApprovedOption,
    ApprovedResponseFragment,
    ExecutionStatus,
    FollowUpRequest,
    GeneratedExecutionOutcome,
    ResponseFragmentKind,
)


def direct_result_output(
    session: CommerceSession, result: DirectCartResult, quantity: Decimal
) -> CapabilityOutput[CommerceSession]:
    if result.kind is DirectCartResultKind.ADDED:
        assert result.product is not None and result.cart is not None
        amount = format(quantity, "f")
        product = result.product
        updated = session.model_copy(
            update={
                "cart_items": result.cart.items,
                "selected_product": product,
                "pending_cart_addition": None,
                "checkout": CheckoutState(
                    stage=CheckoutStage.REVIEWING_CART,
                    source_cart_id=result.cart.id,
                    source_cart_version=result.cart.version,
                ),
                "pending_saved_profile_use": None,
                "pending_cart_clear": None,
            }
        )
        return CapabilityOutput(
            session=updated,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.SUCCESS,
                fragments=(
                    ApprovedResponseFragment(
                        id="direct-cart-item-added",
                        text=f"Added {amount} {product.unit} {product.name} to your cart.",
                    ),
                    ApprovedResponseFragment(
                        id="direct-checkout-cart-heading",
                        text="Checkout cart review:",
                    ),
                    *tuple(
                        ApprovedResponseFragment(
                            id=f"direct-checkout-item-{ordinal}",
                            text=(
                                f"{ordinal}. {item.product.name} — "
                                f"{format(item.quantity, 'f')} {item.product.unit} "
                                f"at ₹{item.product.price}/{item.product.unit}"
                            ),
                            kind=ResponseFragmentKind.ITEM,
                        )
                        for ordinal, item in enumerate(result.cart.items, start=1)
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="checkout-or-continue",
                    question="Would you like to checkout or continue shopping?",
                ),
                protected_values=tuple(
                    value
                    for ordinal, item in enumerate(result.cart.items, start=1)
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
    if result.kind is DirectCartResultKind.UNIT_MISMATCH:
        unit = result.canonical_unit or "the catalog unit"
        name = result.product.name if result.product else "That product"
        return _outcome(
            session,
            ExecutionStatus.CONFLICT,
            "direct-cart-unit-mismatch",
            f"{name} is sold by {unit}.",
            "request-catalog-unit-quantity",
            f"How many {unit} would you like?",
            (name, unit),
        )
    if result.kind is DirectCartResultKind.UNAVAILABLE:
        return _outcome(
            session,
            ExecutionStatus.CONFLICT,
            "direct-cart-product-unavailable",
            "That product is currently unavailable and was not added to your cart.",
            "search-alternative-product",
            "What alternative product would you like to search for?",
        )
    if result.kind is DirectCartResultKind.NOT_FOUND:
        return _outcome(
            session,
            ExecutionStatus.NOT_FOUND,
            "direct-cart-product-not-found",
            "I could not find that product in the catalog.",
            "request-product-search",
            "What product would you like to search for?",
        )
    raise ValueError(f"Unsupported direct cart result: {result.kind}")


def ambiguous_output(
    session: CommerceSession, result: DirectCartResult
) -> CapabilityOutput[CommerceSession]:
    return CapabilityOutput(
        session=session,
        outcome=GeneratedExecutionOutcome(
            status=ExecutionStatus.CONFLICT,
            fragments=(
                ApprovedResponseFragment(
                    id="direct-cart-product-ambiguous",
                    text="More than one catalog product matches your request.",
                ),
            ),
            follow_up=FollowUpRequest(
                id="select-product-for-cart-addition",
                question="Which product would you like to add?",
                options=tuple(
                    ApprovedOption(
                        id=f"pending-product-{i}", label=f"{i}. {option.display_name}"
                    )
                    for i, option in enumerate(result.options, 1)
                ),
            ),
            protected_values=tuple(
                value
                for i, option in enumerate(result.options, 1)
                for value in (str(i), option.display_name)
            ),
        ),
    )


def _outcome(session, status, fragment_id, text, follow_up_id, question, protected=()):
    return CapabilityOutput(
        session=session,
        outcome=GeneratedExecutionOutcome(
            status=status,
            fragments=(ApprovedResponseFragment(id=fragment_id, text=text),),
            follow_up=FollowUpRequest(id=follow_up_id, question=question),
            protected_values=protected,
        ),
    )

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field, ValidationError

from commerce.models import CheckoutState, CommerceSession
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


class AddToCartArguments(BaseModel):
    quantity: Decimal = Field(gt=0, allow_inf_nan=False)


class AddToCartCapability(Capability[CommerceSession]):
    def __init__(self, service: CartService) -> None:
        self._service = service

    @property
    def metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            name=CapabilityName.ADD_TO_CART,
            description=(
                "Adds the selected product to the cart with a positive quantity. "
                "Requires a decimal 'quantity' argument."
            ),
        )

    async def execute(
        self,
        input: CapabilityInput[CommerceSession],
    ) -> CapabilityOutput[CommerceSession]:
        product = input.session.selected_product
        if product is None:
            return self._missing_product(input.session)

        if "quantity" not in input.data:
            return self._invalid_quantity(
                input.session,
                ExecutionStatus.MISSING_INPUT,
            )

        try:
            arguments = AddToCartArguments.model_validate(input.data)
        except ValidationError:
            return self._invalid_quantity(
                input.session,
                ExecutionStatus.INVALID_INPUT,
            )

        cart = await self._service.add_or_replace(
            input.context.tenant_id,
            input.context.conversation_id,
            product,
            arguments.quantity,
        )
        session = input.session.model_copy(
            update={
                "cart_items": cart.items,
                "checkout": CheckoutState(),
                "pending_saved_profile_use": None,
                "pending_cart_clear": None,
                "pending_cart_addition": None,
            }
        )
        quantity = format(arguments.quantity, "f")
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.SUCCESS,
                fragments=(
                    ApprovedResponseFragment(
                        id="cart-item-added",
                        text=(
                            f"Added {quantity} {product.unit} {product.name} "
                            "to your cart."
                        ),
                    ),
                ),
                follow_up=FollowUpRequest(
                                    id="confirm-cart-order",
                                    question=(
                                        f"You have {quantity} {product.unit} of "
                                        f"{product.name} in your cart. Would you like "
                                        "to proceed to checkout or continue shopping?"
                                    ),
                                ),
                protected_values=(quantity, product.unit, product.name),
            ),
        )

    @staticmethod
    def _missing_product(
        session: CommerceSession,
    ) -> CapabilityOutput[CommerceSession]:
        if session.recent_product_results:
            follow_up = FollowUpRequest(
                id="select-product-for-cart",
                question="Which product would you like to select?",
                options=tuple(
                    ApprovedOption(
                        id=f"product-{ordinal}",
                        label=f"{ordinal}. {product.name}",
                    )
                    for ordinal, product in enumerate(
                        session.recent_product_results,
                        start=1,
                    )
                ),
            )
        else:
            follow_up = FollowUpRequest(
                id="search-product-for-cart",
                question="What product would you like to search for?",
            )

        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.MISSING_INPUT,
                fragments=(
                    ApprovedResponseFragment(
                        id="missing-selected-product",
                        text="Please select a product before adding it to your cart.",
                    ),
                ),
                follow_up=follow_up,
                protected_values=tuple(
                    value
                    for ordinal, product in enumerate(
                        session.recent_product_results, start=1
                    )
                    for value in (str(ordinal), product.name)
                ),
            ),
        )

    @staticmethod
    def _invalid_quantity(
        session: CommerceSession,
        status: ExecutionStatus,
    ) -> CapabilityOutput[CommerceSession]:
        product = session.selected_product
        if product is None:
            raise ValueError("Selected product is required for quantity clarification.")

        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=status,
                fragments=(
                    ApprovedResponseFragment(
                        id="invalid-cart-quantity",
                        text="Please provide a quantity greater than zero.",
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="request-cart-quantity",
                    question=(
                        f"How much {product.unit} of {product.name} would you like "
                        "to add?"
                    ),
                ),
                protected_values=(product.unit, product.name),
            ),
        )

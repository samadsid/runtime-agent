from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from commerce.models import CommerceSession, DirectCartResultKind, PendingCartAddition
from commerce.services import DirectCartService, DirectCartServiceError, UnitPolicy
from runtime.capabilities import (
    Capability,
    CapabilityInput,
    CapabilityMetadata,
    CapabilityOutput,
)
from runtime.capabilities.direct_cart_support import (
    ambiguous_output,
    direct_result_output,
)
from runtime.contracts import (
    ApprovedResponseFragment,
    ExecutionStatus,
    FollowUpRequest,
    GeneratedExecutionOutcome,
)

NonEmptyProductText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
NonEmptyUnitText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)
]


class AddProductToCartArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_query: NonEmptyProductText
    quantity: Decimal = Field(gt=0, allow_inf_nan=False)
    stated_unit: NonEmptyUnitText | None = None


class AddProductToCartCapability(Capability[CommerceSession]):
    def __init__(self, service: DirectCartService) -> None:
        self._service = service
        self._units = UnitPolicy()

    @property
    def metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            name="add_product_to_cart",
            description="Resolves and adds one uniquely matching catalog product; multiple matches require a pending ordinal selection.",
        )

    async def execute(
        self, input: CapabilityInput[CommerceSession]
    ) -> CapabilityOutput[CommerceSession]:
        try:
            arguments = AddProductToCartArguments.model_validate(input.data)
        except ValidationError:
            return CapabilityOutput(
                session=input.session.model_copy(
                    update={"pending_cart_addition": None}
                ),
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.INVALID_INPUT,
                    fragments=(
                        ApprovedResponseFragment(
                            id="invalid-direct-cart-product",
                            text="A product and positive quantity are required.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="request-direct-cart-product",
                        question="What product and quantity would you like to add?",
                    ),
                ),
            )
        request_id = input.context.request_id
        if request_id is None or not request_id.strip():
            return CapabilityOutput(
                session=input.session.model_copy(
                    update={"pending_cart_addition": None}
                ),
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.FAILURE,
                    fragments=(
                        ApprovedResponseFragment(
                            id="direct-cart-temporarily-unavailable",
                            text="The cart addition could not be completed safely.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="retry-direct-cart-addition",
                        question="Would you like to retry this cart addition?",
                    ),
                ),
            )
        try:
            result = await self._service.resolve_and_add(
                tenant_id=input.context.tenant_id,
                conversation_id=input.context.conversation_id,
                product_query=arguments.product_query,
                quantity=arguments.quantity,
                stated_unit=arguments.stated_unit,
                request_id=request_id,
            )
        except DirectCartServiceError:
            return CapabilityOutput(
                session=input.session.model_copy(
                    update={"pending_cart_addition": None}
                ),
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.FAILURE,
                    fragments=(
                        ApprovedResponseFragment(
                            id="direct-cart-temporarily-unavailable",
                            text="The cart addition could not be completed safely.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="retry-direct-cart-addition",
                        question="Would you like to retry this cart addition?",
                    ),
                ),
            )
        if result.kind is DirectCartResultKind.AMBIGUOUS:
            pending = PendingCartAddition(
                options=result.options,
                quantity=arguments.quantity,
                stated_unit=(
                    self._units.normalize(arguments.stated_unit)
                    if arguments.stated_unit
                    else None
                ),
                created_at=datetime.now(timezone.utc),
                source_request_id=request_id,
            )
            return ambiguous_output(
                input.session.model_copy(update={"pending_cart_addition": pending}),
                result,
            )
        base = input.session.model_copy(update={"pending_cart_addition": None})
        return direct_result_output(base, result, arguments.quantity)

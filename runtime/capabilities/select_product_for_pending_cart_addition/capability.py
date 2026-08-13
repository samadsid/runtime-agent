from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from commerce.models import CommerceSession, DirectCartResultKind
from commerce.services import DirectCartService, DirectCartServiceError
from runtime.capabilities import (
    Capability,
    CapabilityInput,
    CapabilityMetadata,
    CapabilityOutput,
)
from runtime.capabilities.direct_cart_support import direct_result_output
from runtime.contracts import (
    ApprovedOption,
    ApprovedResponseFragment,
    ExecutionStatus,
    FollowUpRequest,
    GeneratedExecutionOutcome,
)


class SelectPendingCartProductArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ordinal: int | None = Field(default=None, strict=True, ge=1)
    cancelled: bool | None = Field(default=None, strict=True)

    @model_validator(mode="after")
    def exactly_one_action(self):
        if (self.ordinal is None) == (self.cancelled is not True):
            raise ValueError("Provide exactly one of ordinal or cancelled=true.")
        return self


class SelectProductForPendingCartAdditionCapability(Capability[CommerceSession]):
    def __init__(
        self,
        service: DirectCartService,
        ttl: timedelta = timedelta(minutes=15),
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._service = service
        self._ttl = ttl
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @property
    def metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            name="select_product_for_pending_cart_addition",
            description="Selects only from pending direct-add options, or cancels that pending addition.",
        )

    async def execute(
        self, input: CapabilityInput[CommerceSession]
    ) -> CapabilityOutput[CommerceSession]:
        try:
            arguments = SelectPendingCartProductArguments.model_validate(input.data)
        except ValidationError:
            return self._invalid(input.session)
        pending = input.session.pending_cart_addition
        if pending is None or self._clock() - pending.created_at > self._ttl:
            return CapabilityOutput(
                session=input.session.model_copy(
                    update={"pending_cart_addition": None}
                ),
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.NOT_FOUND,
                    fragments=(
                        ApprovedResponseFragment(
                            id="pending-cart-addition-expired",
                            text="That pending product selection is no longer available.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="request-direct-cart-product",
                        question="What product and quantity would you like to add?",
                    ),
                ),
            )
        if arguments.cancelled:
            return CapabilityOutput(
                session=input.session.model_copy(
                    update={"pending_cart_addition": None}
                ),
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.SUCCESS,
                    fragments=(
                        ApprovedResponseFragment(
                            id="pending-cart-addition-cancelled",
                            text="The pending cart addition was cancelled.",
                        ),
                    ),
                ),
            )
        assert arguments.ordinal is not None
        if arguments.ordinal > len(pending.options):
            return self._invalid(input.session)
        request_id = input.context.request_id
        if request_id is None or not request_id.strip():
            return CapabilityOutput(
                session=input.session,
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
        option = pending.options[arguments.ordinal - 1]
        try:
            result = await self._service.add_pending_selection(
                tenant_id=input.context.tenant_id,
                conversation_id=input.context.conversation_id,
                product_id=option.product_id,
                quantity=pending.quantity,
                stated_unit=pending.stated_unit,
                request_id=request_id,
            )
        except DirectCartServiceError:
            return CapabilityOutput(
                session=input.session,
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
        if result.kind is DirectCartResultKind.UNAVAILABLE:
            return direct_result_output(
                input.session.model_copy(update={"pending_cart_addition": None}),
                result,
                pending.quantity,
            )
        return direct_result_output(input.session, result, pending.quantity)

    @staticmethod
    def _invalid(session: CommerceSession) -> CapabilityOutput[CommerceSession]:
        pending = session.pending_cart_addition
        options = pending.options if pending else ()
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.INVALID_INPUT,
                fragments=(
                    ApprovedResponseFragment(
                        id="invalid-pending-cart-product-ordinal",
                        text="That number does not match a pending product option.",
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="correct-pending-cart-product-ordinal",
                    question="Which available product number would you like?",
                    options=tuple(
                        ApprovedOption(
                            id=f"pending-product-{i}",
                            label=f"{i}. {option.display_name}",
                        )
                        for i, option in enumerate(options, 1)
                    ),
                ),
                protected_values=tuple(
                    value
                    for i, option in enumerate(options, 1)
                    for value in (str(i), option.display_name)
                ),
            ),
        )

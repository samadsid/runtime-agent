from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError

from commerce.models import CommerceSession
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


class SelectProductArguments(BaseModel):
    ordinal: int = Field(strict=True, ge=1)


class SelectProductCapability(Capability[CommerceSession]):
    @property
    def metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            name=CapabilityName.SELECT_PRODUCT,
            description=(
                "Selects a product from the most recent search results. "
                "Requires a 1-based integer 'ordinal' argument."
            ),
        )

    async def execute(
        self,
        input: CapabilityInput[CommerceSession],
    ) -> CapabilityOutput[CommerceSession]:
        if "ordinal" not in input.data:
            return self._missing_ordinal(input.session)

        try:
            arguments = SelectProductArguments.model_validate(input.data)
        except ValidationError:
            return self._invalid_ordinal(input.session)

        if not input.session.recent_product_results:
            return CapabilityOutput(
                session=input.session,
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.NOT_FOUND,
                    fragments=(
                        ApprovedResponseFragment(
                            id="no-recent-results",
                            text="There are no recent product results to select from.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="request-product-search",
                        question="What product would you like to search for?",
                    ),
                ),
            )

        index = arguments.ordinal - 1
        if index >= len(input.session.recent_product_results):
            return self._invalid_ordinal(input.session)

        product = input.session.recent_product_results[index]
        session = input.session.model_copy(update={"selected_product": product})

        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.SUCCESS,
                fragments=(
                    ApprovedResponseFragment(
                        id="selected-product",
                        text=f"Selected {product.name}.",
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="quantity-request",
                    question="Please specify the quantity you would like to order.",
                ),
            ),
        )

    @staticmethod
    def _missing_ordinal(
        session: CommerceSession,
    ) -> CapabilityOutput[CommerceSession]:
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.MISSING_INPUT,
                fragments=(
                    ApprovedResponseFragment(
                        id="missing-ordinal",
                        text="I need the number of the product you want to select.",
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="request-ordinal",
                    question="Which product number would you like to select?",
                    options=SelectProductCapability._options(session),
                ),
            ),
        )

    @staticmethod
    def _invalid_ordinal(
        session: CommerceSession,
    ) -> CapabilityOutput[CommerceSession]:
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.INVALID_INPUT,
                fragments=(
                    ApprovedResponseFragment(
                        id="invalid-ordinal",
                        text="That product number does not match an available option.",
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="correct-ordinal",
                    question="Which available product number would you like to select?",
                    options=SelectProductCapability._options(session),
                ),
            ),
        )

    @staticmethod
    def _options(session: CommerceSession) -> tuple[ApprovedOption, ...]:
        return tuple(
            ApprovedOption(
                id=f"product-{ordinal}",
                label=f"{ordinal}. {product.name}",
            )
            for ordinal, product in enumerate(
                session.recent_product_results,
                start=1,
            )
        )

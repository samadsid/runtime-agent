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
        try:
            arguments = SelectProductArguments.model_validate(input.data)
        except ValidationError:
            return self._clarification(input.session)

        index = arguments.ordinal - 1
        if index >= len(input.session.recent_product_results):
            return self._clarification(input.session)

        product = input.session.recent_product_results[index]
        session = input.session.model_copy(update={"selected_product": product})

        return CapabilityOutput(
            success=True,
            session=session,
            message=f"Selected {product.name}.",
        )

    @staticmethod
    def _clarification(
        session: CommerceSession,
    ) -> CapabilityOutput[CommerceSession]:
        return CapabilityOutput(
            success=False,
            session=session,
            message=(
                "I couldn't match that option to the latest product results. "
                "Please choose one of the available options or search again."
            ),
        )

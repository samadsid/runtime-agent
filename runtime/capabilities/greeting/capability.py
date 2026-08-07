from __future__ import annotations

from commerce.models import CommerceSession
from runtime.capabilities import (
    Capability,
    CapabilityInput,
    CapabilityMetadata,
    CapabilityName,
    CapabilityOutput,
)


class GreetingCapability(Capability[CommerceSession]):
    @property
    def metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            name=CapabilityName.GREETING,
            description="Greets the customer and starts a conversation.",
        )

    async def execute(
        self,
        input: CapabilityInput[CommerceSession],
    ) -> CapabilityOutput[CommerceSession]:

        return CapabilityOutput(
            success=True,
            session=input.session,
            message="Hello! How can I help you today!",
        )

from __future__ import annotations

from commerce.models import CommerceSession
from runtime.capabilities import (
    Capability,
    CapabilityInput,
    CapabilityMetadata,
    CapabilityName,
    CapabilityOutput,
)
from runtime.contracts import (
    ApprovedResponseFragment,
    ExecutionStatus,
    GeneratedExecutionOutcome,
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
            session=input.session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.SUCCESS,
                fragments=(
                    ApprovedResponseFragment(
                        id="greeting",
                        text="MeatUncle is here to help you find the best meat products! How can I assist you today?",
                    ),
                ),
            ),
        )

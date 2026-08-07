from __future__ import annotations

from runtime.contracts import (
    RuntimeRequest,
    RuntimeResponse,
)
from runtime.llm import (
    LLMProvider,
    LLMRequest,
)
from runtime.registry import CapabilityRegistry


class AgentRuntime:

    def __init__(
        self,
        llm_provider: LLMProvider,
        capability_registry: CapabilityRegistry,
    ) -> None:

        self._llm_provider = llm_provider
        self._capability_registry = capability_registry

    async def invoke(
        self,
        request: RuntimeRequest,
    ) -> RuntimeResponse:
        """
        Entry point for every conversation.
        """

        llm_request = LLMRequest(
            messages=request.state.messages,
        )

        llm_response = await self._llm_provider.invoke(
            llm_request
        )

        request.state.messages.append(
            llm_response.message
        )

        return RuntimeResponse(
            message=llm_response.message,
            state=request.state,
        )
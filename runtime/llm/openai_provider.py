from __future__ import annotations

from runtime.contracts import Message, MessageRole

from .provider import LLMProvider
from .request import LLMRequest
from .response import LLMResponse

from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class OpenAIProvider(LLMProvider):

    async def invoke(
        self,
        request: LLMRequest,
        response_model: type[T],
    ) -> T:

        return LLMResponse(
            message=Message(
                role=MessageRole.ASSISTANT,
                content="OpenAI Provider Placeholder",
            )
        )
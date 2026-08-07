from __future__ import annotations

from typing import TypeVar

from langchain_core.messages import (
    SystemMessage,
)
from langchain_ollama import ChatOllama
from pydantic import BaseModel

from app.config.settings import settings
from runtime.contracts import MessageRole
from runtime.llm.provider import LLMProvider
from runtime.llm.request import LLMRequest
from runtime.mappers.message_mapper import MessageMapper

T = TypeVar("T", bound=BaseModel)


class OllamaProvider(LLMProvider):

    def __init__(self):

        self._llm = ChatOllama(
            base_url=settings.OLLAMA_BASE_URL,
            model=settings.OLLAMA_MODEL,
            temperature=settings.LLM_TEMPERATURE,
        )

    async def invoke(
        self,
        request: LLMRequest,
        response_model: type[T],
    ) -> T:

        messages = MessageMapper.to_langchain(
            request.messages
        )


        structured_llm = self._llm.with_structured_output(
            response_model
        )

        return await structured_llm.ainvoke(
            messages
        )
from __future__ import annotations

from typing import TypeVar

from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel

from app.config.settings import settings
from runtime.llm.provider import LLMProvider
from runtime.llm.request import LLMRequest
from runtime.mappers.message_mapper import MessageMapper

T = TypeVar("T", bound=BaseModel)


class GeminiProvider(LLMProvider):
    def __init__(self) -> None:
        self._llm = ChatGoogleGenerativeAI(
            model=settings.GEMINI_MODEL,
            google_api_key=settings.GEMINI_API_KEY,
            temperature=settings.LLM_TEMPERATURE,
        )

    async def invoke(
        self,
        request: LLMRequest,
        response_model: type[T],
    ) -> T:
        messages = MessageMapper.to_langchain(request.messages)

        structured_llm = self._llm.with_structured_output(
            response_model,
        )

        return await structured_llm.ainvoke(messages)
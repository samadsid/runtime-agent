from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from runtime.contracts import Message


class LLMRequest(BaseModel):
    """
    Provider-agnostic request sent to an LLM.
    """

    messages: list[Message]

    temperature: float = 0.2

    max_tokens: int | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)
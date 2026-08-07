from __future__ import annotations

from pydantic import BaseModel

from runtime.contracts import Message


class LLMResponse(BaseModel):
    message: Message
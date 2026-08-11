from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, StringConstraints

ChatMessage = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=2_000),
]


class ChatRequest(BaseModel):
    message: ChatMessage
    conversation_id: UUID | None = None


class ChatResponse(BaseModel):
    conversation_id: UUID
    reply: str

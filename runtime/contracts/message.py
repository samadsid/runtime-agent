from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class Message(BaseModel):
    id: UUID = Field(default_factory=uuid4)

    role: MessageRole

    content: str

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @classmethod
    def user(
        cls,
        content: str,
    ) -> "Message":
        return cls(
            role=MessageRole.USER,
            content=content,
        )

    @classmethod
    def assistant(
        cls,
        content: str,
    ) -> "Message":
        return cls(
            role=MessageRole.ASSISTANT,
            content=content,
        )

    @classmethod
    def system(
        cls,
        content: str,
    ) -> "Message":
        return cls(
            role=MessageRole.SYSTEM,
            content=content,
        )

    @classmethod
    def tool(
        cls,
        content: str,
    ) -> "Message":
        return cls(
            role=MessageRole.TOOL,
            content=content,
        )
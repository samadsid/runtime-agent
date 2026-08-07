from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from .message import Message


class ConversationState(BaseModel):

    conversation_id: UUID

    messages: list[Message] = Field(default_factory=list)

    context: dict[str, Any] = Field(default_factory=dict)

    metadata: dict[str, Any] = Field(default_factory=dict)

    def add_message(
        self,
        message: Message,
    ) -> None:

        self.messages.append(message)

    def add_user_message(
        self,
        content: str,
    ) -> None:

        self.add_message(
            Message.user(content)
        )

    def add_assistant_message(
        self,
        content: str,
    ) -> None:

        self.add_message(
            Message.assistant(content)
        )

    def add_system_message(
        self,
        content: str,
    ) -> None:

        self.add_message(
            Message.system(content)
        )

    def add_tool_message(
        self,
        content: str,
    ) -> None:

        self.add_message(
            Message.tool(content)
        )

    @property
    def latest_message(
        self,
    ) -> Message | None:

        if not self.messages:
            return None

        return self.messages[-1]
from __future__ import annotations

from uuid import UUID, uuid4

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)

from runtime.contracts import (
    Message,
    MessageRole,
)

from .message_adapter import MessageAdapter


class LangChainMessageAdapter(MessageAdapter):
    def to_framework(
        self,
        message: Message,
    ) -> BaseMessage:

        if message.role == MessageRole.USER:
            return HumanMessage(
                content=message.content,
                id=str(message.id),
            )

        if message.role == MessageRole.ASSISTANT:
            return AIMessage(
                content=message.content,
                id=str(message.id),
            )

        if message.role == MessageRole.SYSTEM:
            return SystemMessage(
                content=message.content,
                id=str(message.id),
            )

        raise ValueError(f"Unsupported role: {message.role}")

    def from_framework(
        self,
        message: BaseMessage,
    ) -> Message:

        if isinstance(message, HumanMessage):
            role = MessageRole.USER

        elif isinstance(message, AIMessage):
            role = MessageRole.ASSISTANT

        elif isinstance(message, SystemMessage):
            role = MessageRole.SYSTEM

        else:
            raise TypeError(f"Unsupported message type: {type(message)}")

        if not isinstance(message.content, str):
            raise TypeError("Only text message content is supported.")
        return Message(
            id=(
                message.id
                if isinstance(message.id, UUID)
                else UUID(str(message.id))
                if message.id
                else uuid4()
            ),
            role=role,
            content=message.content,
        )

    def to_framework_messages(
        self,
        messages: list[Message],
    ) -> list[BaseMessage]:

        return [self.to_framework(message) for message in messages]

    def from_framework_messages(
        self,
        messages: list[BaseMessage],
    ) -> list[Message]:

        return [self.from_framework(message) for message in messages]

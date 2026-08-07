from __future__ import annotations

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    BaseMessage,
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
            )

        if message.role == MessageRole.ASSISTANT:
            return AIMessage(
                content=message.content,
            )

        if message.role == MessageRole.SYSTEM:
            return SystemMessage(
                content=message.content,
            )

        raise ValueError(
            f"Unsupported role: {message.role}"
        )
        
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
            raise ValueError(
                f"Unsupported message type: {type(message)}"
            )

        return Message(
            role=role,
            content=message.content,
        )
        
    def to_framework_messages(
        self,
        messages: list[Message],
    ) -> list[BaseMessage]:

        return [
            self.to_framework(message)
            for message in messages
        ]
        
    def from_framework_messages(
        self,
        messages: list[BaseMessage],
    ) -> list[Message]:

        return [
            self.from_framework(message)
            for message in messages
        ]
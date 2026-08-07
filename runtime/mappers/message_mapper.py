from __future__ import annotations

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from runtime.contracts import (
    Message,
    MessageRole,
)


class MessageMapper:

    @staticmethod
    def to_langchain(
        messages: list[Message],
    ) -> list[BaseMessage]:

        result: list[BaseMessage] = []

        for message in messages:
            result.append(
                MessageMapper.to_langchain_message(
                    message
                )
            )

        return result

    @staticmethod
    def to_langchain_message(
        message: Message,
    ) -> BaseMessage:

        if message.role == MessageRole.USER:
            return HumanMessage(
                content=message.content
            )

        if message.role == MessageRole.ASSISTANT:
            return AIMessage(
                content=message.content
            )

        if message.role == MessageRole.SYSTEM:
            return SystemMessage(
                content=message.content
            )

        if message.role == MessageRole.TOOL:
            return ToolMessage(
                content=message.content,
                tool_call_id="runtime",
            )

        raise ValueError(
            f"Unsupported role: {message.role}"
        )

    @staticmethod
    def from_langchain(
        message: BaseMessage,
    ) -> Message:

        if isinstance(message, HumanMessage):
            return Message(
                role=MessageRole.USER,
                content=str(message.content),
            )

        if isinstance(message, AIMessage):
            return Message(
                role=MessageRole.ASSISTANT,
                content=str(message.content),
            )

        if isinstance(message, SystemMessage):
            return Message(
                role=MessageRole.SYSTEM,
                content=str(message.content),
            )

        if isinstance(message, ToolMessage):
            return Message(
                role=MessageRole.TOOL,
                content=str(message.content),
            )

        raise ValueError(
            f"Unsupported LangChain message: {type(message)}"
        )
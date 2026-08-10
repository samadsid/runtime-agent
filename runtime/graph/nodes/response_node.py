from typing import Any

from runtime.contracts import Message, MessageRole
from runtime.graph.adapters import MessageAdapter
from runtime.graph.state import CommerceGraphState
from runtime.responses import ResponseGenerator


class ResponseNode:
    def __init__(
        self,
        response_generator: ResponseGenerator,
        message_adapter: MessageAdapter,
    ) -> None:
        self._response_generator = response_generator
        self._message_adapter = message_adapter

    async def __call__(
        self,
        state: CommerceGraphState,
    ) -> dict[str, Any]:
        if state.execution_outcome is None:
            raise ValueError(
                "Execution outcome is required before response generation."
            )

        messages = self._message_adapter.from_framework_messages(state.messages)
        customer_message = next(
            (
                message.content
                for message in reversed(messages)
                if message.role == MessageRole.USER
            ),
            "",
        )

        message = await self._response_generator.generate(
            state.execution_outcome,
            customer_message,
        )

        assistant_message = self._message_adapter.to_framework(
            Message.assistant(message)
        )
        return {"messages": [assistant_message]}

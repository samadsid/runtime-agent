from typing import Any

from commerce.models import CommerceSession
from runtime.contracts import Message
from runtime.graph.adapters import MessageAdapter
from runtime.graph.state import CommerceGraphState
from runtime.handlers import CommandHandler


class ExecuteNode:
    def __init__(
        self,
        command_handler: CommandHandler,
        message_adapter: MessageAdapter,
    ) -> None:
        self._command_handler = command_handler
        self._message_adapter = message_adapter

    async def __call__(
        self,
        state: CommerceGraphState,
    ) -> dict[str, Any]:

        if state.planner_response is None:
            raise ValueError("Planner response is required before execution.")

        result = await self._command_handler.handle(
            state.planner_response.command,
            state.session or CommerceSession(),
        )

        assistant_message = self._message_adapter.to_framework(
            Message.assistant(
                result.message,
            )
        )

        return {
            "messages": [
                assistant_message,
            ],
            "session": result.session,
        }

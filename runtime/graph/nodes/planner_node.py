from typing import Any

from commerce.models import CommerceSession
from runtime.graph.adapters import MessageAdapter
from runtime.graph.state import CommerceGraphState
from runtime.planner import Planner


class PlannerNode:
    def __init__(
        self,
        planner: Planner,
        message_adapter: MessageAdapter,
    ) -> None:
        self._planner = planner
        self._message_adapter = message_adapter

    async def __call__(
        self,
        state: CommerceGraphState,
    ) -> dict[str, Any]:

        messages = self._message_adapter.from_framework_messages(
            state.messages,
        )

        planner_response = await self._planner.plan(
            messages,
            state.session or CommerceSession(),
        )

        return {
            "planner_response": planner_response,
        }

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

        print("====================Planner Node called======================")

        messages = self._message_adapter.from_framework_messages(
            state.messages,
        )

        # print("===== Messages in Planner =====")
        # for message in messages:
        #     print(type(message).__name__, ":", message.content)
        # print("===============================")

        planner_response = await self._planner.plan(
            messages,
            state.session or CommerceSession(),
        )

        print("===== Planner Node Response =====")
        print(planner_response)
        print("=============================================")

        return {
            "planner_response": planner_response,
        }

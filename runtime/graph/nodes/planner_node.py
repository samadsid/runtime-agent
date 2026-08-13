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

        session = state.session or CommerceSession()
        if isinstance(self._planner, Planner):
            planner_response = await self._planner.plan(
                messages, session, state.customer_profile_projection
            )
        else:
            # Preserve the narrow planner test-double protocol used by graph tests.
            planner_response = await self._planner.plan(messages, session)

        return {
            "planner_response": planner_response,
        }

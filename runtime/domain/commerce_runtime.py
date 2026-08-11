from __future__ import annotations

from runtime.contracts import ConversationState, CustomerChannelContext
from runtime.graph import CommerceGraph
from runtime.graph.adapters import GraphStateAdapter


class CommerceRuntime:
    def __init__(
        self,
        graph: CommerceGraph,
        graph_state_adapter: GraphStateAdapter,
    ) -> None:

        self._graph = graph
        self._graph_state_adapter = graph_state_adapter

    async def chat(
        self,
        conversation: ConversationState,
        customer_context: CustomerChannelContext,
    ) -> ConversationState:
        graph_state = self._graph_state_adapter.to_graph_state(
            conversation, customer_context
        )

        graph_state = await self._graph.invoke(graph_state)

        conversation = self._graph_state_adapter.from_graph_state(graph_state)

        return conversation

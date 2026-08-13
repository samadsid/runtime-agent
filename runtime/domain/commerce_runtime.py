from __future__ import annotations

from commerce.models import CustomerProfileProjection
from commerce.repositories import SavedDeliveryPersistenceError
from commerce.services import SavedDeliveryDetailsService
from runtime.contracts import ConversationState, CustomerChannelContext
from runtime.graph import CommerceGraph
from runtime.graph.adapters import GraphStateAdapter


class CommerceRuntime:
    def __init__(
        self,
        graph: CommerceGraph,
        graph_state_adapter: GraphStateAdapter,
        saved_delivery_details_service: SavedDeliveryDetailsService,
    ) -> None:

        self._graph = graph
        self._graph_state_adapter = graph_state_adapter
        self._saved_delivery_details_service = saved_delivery_details_service

    async def chat(
        self,
        conversation: ConversationState,
        customer_context: CustomerChannelContext,
    ) -> ConversationState:
        graph_state = self._graph_state_adapter.to_graph_state(
            conversation, customer_context
        )
        try:
            projection = (
                await self._saved_delivery_details_service.get_profile_projection(
                    customer_context.tenant_id,
                    customer_context.channel,
                    customer_context.channel_customer_id,
                )
            )
        except SavedDeliveryPersistenceError:
            projection = CustomerProfileProjection(hydration_failed=True)
        graph_state = graph_state.model_copy(
            update={"customer_profile_projection": projection}
        )

        graph_state = await self._graph.invoke(graph_state)

        conversation = self._graph_state_adapter.from_graph_state(graph_state)

        return conversation

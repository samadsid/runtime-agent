from __future__ import annotations

from uuid import UUID

from commerce.models import ChannelName
from runtime.contracts import ConversationState, CustomerChannelContext
from runtime.graph.adapters.graph import GraphStateAdapter
from runtime.graph.adapters.messages import MessageAdapter
from runtime.graph.state import CommerceGraphState


class ConversationStateAdapter(GraphStateAdapter):
    def __init__(self, message_adapter: MessageAdapter) -> None:
        self._message_adapter = message_adapter

    def to_graph_state(
        self,
        conversation: ConversationState,
        customer_context: CustomerChannelContext | None = None,
    ) -> CommerceGraphState:
        customer_context = customer_context or CustomerChannelContext(
            tenant_id=UUID(int=0),
            conversation_id=conversation.conversation_id,
            channel=ChannelName.DEVELOPMENT_HTTP,
            channel_customer_id=None,
        )
        if conversation.conversation_id != customer_context.conversation_id:
            raise ValueError("Conversation and trusted context IDs must match.")
        return CommerceGraphState(
            conversation_id=conversation.conversation_id,
            customer_context=customer_context,
            messages=self._message_adapter.to_framework_messages(conversation.messages),
        )

    def from_graph_state(
        self,
        state: CommerceGraphState,
    ) -> ConversationState:
        return ConversationState(
            conversation_id=state.conversation_id,
            messages=self._message_adapter.from_framework_messages(state.messages),
        )

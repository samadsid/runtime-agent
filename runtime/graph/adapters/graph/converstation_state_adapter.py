from __future__ import annotations

from uuid import UUID

from runtime.contracts import ConversationState
from runtime.graph.adapters.graph import GraphStateAdapter
from runtime.graph.adapters.messages import MessageAdapter
from runtime.graph.state import CommerceGraphState


class ConversationStateAdapter(GraphStateAdapter):

    def __init__(
        self, message_adapter: MessageAdapter, tenant_id: UUID | None = None
    ) -> None:
        self._message_adapter = message_adapter
        self._tenant_id = tenant_id or UUID(int=0)
        
        
    def to_graph_state(
        self,
        conversation: ConversationState,
    ) -> CommerceGraphState:
            return CommerceGraphState(
                conversation_id=conversation.conversation_id,
                tenant_id=self._tenant_id,
                messages=self._message_adapter.to_framework_messages(
                    conversation.messages
                ),
            )
            
    def from_graph_state(
        self,
        state: CommerceGraphState,
    ) -> ConversationState:
            return ConversationState(
                conversation_id=state.conversation_id,
                messages=self._message_adapter.from_framework_messages(
                    state.messages
                ),
            )

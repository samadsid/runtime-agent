from __future__ import annotations

from runtime.contracts import ConversationState

from runtime.graph.state import CommerceGraphState


from runtime.graph.adapters.graph import GraphStateAdapter

from runtime.graph.adapters.messages import MessageAdapter


class ConversationStateAdapter(GraphStateAdapter):

    def __init__(self, message_adapter: MessageAdapter) -> None:
        self._message_adapter = message_adapter
        
        
    def to_graph_state(
        self,
        conversation: ConversationState,
    ) -> CommerceGraphState:
            return CommerceGraphState(
                conversation_id=conversation.conversation_id,
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
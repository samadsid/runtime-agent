from __future__ import annotations

from abc import ABC, abstractmethod

from runtime.contracts import ConversationState, CustomerChannelContext
from runtime.graph.state import CommerceGraphState


class GraphStateAdapter(ABC):
    """
    Converts between the application's domain state and the
    runtime graph state.
    """

    @abstractmethod
    def to_graph_state(
        self,
        conversation: ConversationState,
        customer_context: CustomerChannelContext | None = None,
    ) -> CommerceGraphState:
        """
        Convert a ConversationState into a CommerceGraphState.
        """
        raise NotImplementedError

    @abstractmethod
    def from_graph_state(
        self,
        state: CommerceGraphState,
    ) -> ConversationState:
        """
        Convert a CommerceGraphState back into a ConversationState.
        """
        raise NotImplementedError

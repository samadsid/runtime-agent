from __future__ import annotations

from uuid import UUID


class ConversationThread:
    """
    Represents a conversation thread used by the graph runtime.
    """

    def __init__(
        self,
        conversation_id: UUID,
    ) -> None:
        self._conversation_id = conversation_id

    @property
    def id(self) -> str:
        """
        LangGraph expects thread_id as a string.
        """
        return str(self._conversation_id)
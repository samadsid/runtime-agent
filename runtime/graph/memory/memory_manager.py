from __future__ import annotations

from runtime.graph.memory.checkpointer import GraphCheckpointer


class MemoryManager:
    """
    Coordinates graph memory components.

    Today:
        - Checkpointer

    Future:
        - Conversation summaries
        - Long-term memory
        - Semantic retrieval
        - TTL
        - Metrics
    """

    def __init__(
        self,
        checkpointer: GraphCheckpointer,
    ) -> None:
        self._checkpointer = checkpointer

    @property
    def checkpointer(self):
        return self._checkpointer.instance
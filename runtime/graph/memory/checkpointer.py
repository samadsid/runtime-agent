from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from commerce.models import CommerceSession, Product


class GraphCheckpointer:
    """
    Wrapper around LangGraph's checkpointer.

    The rest of the application should never import
    MemorySaver directly.
    """

    def __init__(self) -> None:
        serializer = JsonPlusSerializer(
            allowed_msgpack_modules=(
                CommerceSession,
                Product,
            ),
        )
        self._checkpointer = MemorySaver(
            serde=serializer,
        )

    @property
    def instance(self) -> MemorySaver:
        return self._checkpointer

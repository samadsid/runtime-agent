from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

SessionT = TypeVar("SessionT")


class HandlerResult(BaseModel, Generic[SessionT]):
    """
    Final result produced by a command handler.
    """

    message: str
    session: SessionT

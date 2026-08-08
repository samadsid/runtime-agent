from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

from runtime.contracts import ExecutionOutcome

SessionT = TypeVar("SessionT")


class HandlerResult(BaseModel, Generic[SessionT]):
    """
    Final result produced by a command handler.
    """

    outcome: ExecutionOutcome
    session: SessionT

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

from runtime.contracts import ExecutionOutcome

SessionT = TypeVar("SessionT")


class CapabilityOutput(BaseModel, Generic[SessionT]):
    session: SessionT
    outcome: ExecutionOutcome

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

SessionT = TypeVar("SessionT")


class CapabilityInput(BaseModel, Generic[SessionT]):
    data: dict[str, Any] = Field(default_factory=dict)
    session: SessionT

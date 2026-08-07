from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

SessionT = TypeVar("SessionT")


class CapabilityOutput(BaseModel, Generic[SessionT]):
    success: bool

    session: SessionT

    data: dict[str, Any] = Field(default_factory=dict)

    message: str | None = None

from __future__ import annotations

from typing import Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field

SessionT = TypeVar("SessionT")


class ExecutionContext(BaseModel):
    tenant_id: UUID = UUID(int=0)
    conversation_id: UUID = UUID(int=0)


class CapabilityInput(BaseModel, Generic[SessionT]):
    data: dict[str, Any] = Field(default_factory=dict)
    session: SessionT
    context: ExecutionContext = Field(default_factory=ExecutionContext)

from __future__ import annotations

from typing import Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field

from commerce.models import ChannelName
from runtime.contracts import CustomerChannelContext

SessionT = TypeVar("SessionT")


class ExecutionContext(CustomerChannelContext):
    tenant_id: UUID = UUID(int=0)
    conversation_id: UUID = UUID(int=0)
    channel: ChannelName = ChannelName.DEVELOPMENT_HTTP
    channel_customer_id: str | None = None
    request_id: str | None = None


class CapabilityInput(BaseModel, Generic[SessionT]):
    data: dict[str, Any] = Field(default_factory=dict)
    session: SessionT
    context: ExecutionContext = Field(default_factory=ExecutionContext)

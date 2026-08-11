from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from commerce.models import ChannelName


class CustomerChannelContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    tenant_id: UUID
    conversation_id: UUID
    channel: ChannelName
    channel_customer_id: str | None = None
    request_id: str | None = None

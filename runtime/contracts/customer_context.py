from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from channels.models import InboundLocation, MessageKind
from commerce.models import ChannelName


class TrustedInboundMessageContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    inbound_message_id: UUID
    request_id: str
    message_kind: MessageKind
    location: InboundLocation | None = None


class CustomerChannelContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    tenant_id: UUID
    conversation_id: UUID
    channel: ChannelName
    channel_customer_id: str | None = None
    request_id: str | None = None
    conversation_entry: bool = False
    inbound_message: TrustedInboundMessageContext | None = None

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class EventType(str, Enum):
    USER_MESSAGE = "user.message"
    SYSTEM = "system"
    TIMER = "timer"
    WEBHOOK = "webhook"
    CAPABILITY_RESULT = "capability.result"


class RuntimeEvent(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    type: EventType
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
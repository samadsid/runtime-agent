from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from uuid import UUID


class ChatRequestStatus(str, Enum):
    PENDING = "PENDING"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True)
class ChatRequestRecord:
    tenant_id: UUID
    request_id: UUID
    request_fingerprint: str
    conversation_id: UUID
    status: ChatRequestStatus
    reply: str | None

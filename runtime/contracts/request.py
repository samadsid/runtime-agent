from __future__ import annotations

from pydantic import BaseModel

from .event import RuntimeEvent
from .state import ConversationState


class RuntimeRequest(BaseModel):
    event: RuntimeEvent

    state: ConversationState
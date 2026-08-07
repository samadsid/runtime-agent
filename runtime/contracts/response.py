from __future__ import annotations

from pydantic import BaseModel

from .message import Message
from .state import ConversationState


class RuntimeResponse(BaseModel):
    message: Message

    state: ConversationState
from __future__ import annotations

from pydantic import BaseModel

from runtime.contracts import ConversationState


class PlannerRequest(BaseModel):
    conversation: ConversationState
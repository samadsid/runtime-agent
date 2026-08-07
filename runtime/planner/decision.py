from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DecisionType(str, Enum):
    RESPOND = "respond"
    EXECUTE_CAPABILITY = "execute_capability"
    # WAIT = "wait"


class PlannerDecision(BaseModel):
    type: DecisionType

    message: str | None = None

    capability: str | None = None

    arguments: dict[str, Any] = Field(default_factory=dict)

    reason: str | None = None
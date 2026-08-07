from __future__ import annotations

from typing import Any

from pydantic import Field

from .base import PlannerCommand


class ExecuteCapabilityCommand(PlannerCommand):
    capability: str

    arguments: dict[str, Any] = Field(default_factory=dict)
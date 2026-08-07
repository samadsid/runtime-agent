from __future__ import annotations

from pydantic import BaseModel

from runtime.commands import PlannerCommand


class PlannerResponse(BaseModel):
    command: PlannerCommand
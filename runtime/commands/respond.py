from __future__ import annotations

from .base import PlannerCommand


class RespondCommand(PlannerCommand):
    message: str
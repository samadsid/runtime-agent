from __future__ import annotations

from .base import PlannerCommand


class WaitCommand(PlannerCommand):
    reason: str
from __future__ import annotations

from abc import ABC

from pydantic import BaseModel


class PlannerCommand(BaseModel, ABC):
    """
    Base class for every command produced by the planner.
    """
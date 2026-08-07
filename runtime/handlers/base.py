from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from runtime.commands import PlannerCommand

from .result import HandlerResult

SessionT = TypeVar("SessionT")


class CommandHandlerBase(ABC, Generic[SessionT]):
    @abstractmethod
    async def handle(
        self,
        command: PlannerCommand,
        session: SessionT,
    ) -> HandlerResult[SessionT]:
        raise NotImplementedError

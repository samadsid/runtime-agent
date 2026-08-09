from __future__ import annotations

from typing import Generic, TypeVar

from runtime.capabilities import ExecutionContext
from runtime.commands import (
    ExecuteCapabilityCommand,
    PlannerCommand,
    RespondCommand,
    WaitCommand,
)

from .execute_capability_handler import ExecuteCapabilityHandler
from .respond_handler import RespondHandler
from .result import HandlerResult
from .wait_handler import WaitHandler

SessionT = TypeVar("SessionT")


class CommandHandler(Generic[SessionT]):
    def __init__(
        self,
        respond_handler: RespondHandler[SessionT],
        execute_capability_handler: ExecuteCapabilityHandler[SessionT],
        wait_handler: WaitHandler[SessionT],
    ) -> None:

        self._respond_handler = respond_handler
        self._execute_capability_handler = execute_capability_handler
        self._wait_handler = wait_handler

    async def handle(
        self,
        command: PlannerCommand,
        session: SessionT,
        context: ExecutionContext | None = None,
    ) -> HandlerResult[SessionT]:

        execution_context = context or ExecutionContext()

        if isinstance(command, RespondCommand):
            return await self._respond_handler.handle(command, session, execution_context)

        if isinstance(command, ExecuteCapabilityCommand):
            return await self._execute_capability_handler.handle(
                command, session, execution_context
            )

        if isinstance(command, WaitCommand):
            return await self._wait_handler.handle(command, session, execution_context)

        raise ValueError(f"Unsupported command: {type(command).__name__}")

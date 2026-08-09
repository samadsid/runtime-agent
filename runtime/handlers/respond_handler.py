from typing import Generic, TypeVar

from runtime.capabilities import ExecutionContext
from runtime.commands import RespondCommand
from runtime.contracts import (
    ApprovedResponseFragment,
    ExecutionStatus,
    GeneratedExecutionOutcome,
)

from .base import CommandHandlerBase
from .result import HandlerResult

SessionT = TypeVar("SessionT")


class RespondHandler(CommandHandlerBase[SessionT], Generic[SessionT]):
    async def handle(
        self,
        command: RespondCommand,
        session: SessionT,
        context: ExecutionContext,
    ) -> HandlerResult[SessionT]:

        return HandlerResult(
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.SUCCESS,
                fragments=(
                    ApprovedResponseFragment(
                        id="planner-response", text=command.message
                    ),
                ),
            ),
            session=session,
        )

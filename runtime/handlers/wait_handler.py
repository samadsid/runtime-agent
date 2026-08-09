from typing import Generic, TypeVar

from runtime.capabilities import ExecutionContext
from runtime.commands import WaitCommand
from runtime.contracts import (
    ApprovedResponseFragment,
    ExecutionStatus,
    GeneratedExecutionOutcome,
)

from .base import CommandHandlerBase
from .result import HandlerResult

SessionT = TypeVar("SessionT")


class WaitHandler(CommandHandlerBase[SessionT], Generic[SessionT]):
    async def handle(
        self,
        command: WaitCommand,
        session: SessionT,
        context: ExecutionContext,
    ) -> HandlerResult[SessionT]:

        return HandlerResult(
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.SUCCESS,
                fragments=(
                    ApprovedResponseFragment(id="waiting", text="Waiting..."),
                ),
            ),
            session=session,
        )

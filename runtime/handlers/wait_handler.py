from typing import Generic, TypeVar

from runtime.commands import WaitCommand
from runtime.contracts import ExecutionStatus, FixedExecutionOutcome

from .base import CommandHandlerBase
from .result import HandlerResult

SessionT = TypeVar("SessionT")


class WaitHandler(CommandHandlerBase[SessionT], Generic[SessionT]):
    async def handle(
        self,
        command: WaitCommand,
        session: SessionT,
    ) -> HandlerResult[SessionT]:

        return HandlerResult(
            outcome=FixedExecutionOutcome(
                status=ExecutionStatus.SUCCESS,
                message="Waiting...",
            ),
            session=session,
        )

from typing import Generic, TypeVar

from runtime.commands import WaitCommand

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
            message="Waiting...",
            session=session,
        )

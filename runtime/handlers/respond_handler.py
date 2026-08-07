from typing import Generic, TypeVar

from runtime.commands import RespondCommand

from .base import CommandHandlerBase
from .result import HandlerResult

SessionT = TypeVar("SessionT")


class RespondHandler(CommandHandlerBase[SessionT], Generic[SessionT]):
    async def handle(
        self,
        command: RespondCommand,
        session: SessionT,
    ) -> HandlerResult[SessionT]:

        return HandlerResult(
            message=command.message,
            session=session,
        )

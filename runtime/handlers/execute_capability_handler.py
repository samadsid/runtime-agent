from __future__ import annotations

from typing import Generic, TypeVar

from runtime.capabilities import (
    CapabilityInput,
    CapabilityRegistry,
)
from runtime.commands import ExecuteCapabilityCommand

from .base import CommandHandlerBase
from .result import HandlerResult

SessionT = TypeVar("SessionT")


class ExecuteCapabilityHandler(CommandHandlerBase[SessionT], Generic[SessionT]):
    def __init__(
        self,
        registry: CapabilityRegistry[SessionT],
    ) -> None:
        self._registry = registry

    async def handle(
        self,
        command: ExecuteCapabilityCommand,
        session: SessionT,
    ) -> HandlerResult[SessionT]:

        capability = self._registry.get(command.capability)

        output = await capability.execute(
            CapabilityInput(
                data=command.arguments,
                session=session,
            )
        )

        return HandlerResult(
            outcome=output.outcome,
            session=output.session,
        )

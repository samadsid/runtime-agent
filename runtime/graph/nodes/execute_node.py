import logging
from typing import Any

from commerce.models import CommerceSession
from runtime.contracts import (
    ApprovedResponseFragment,
    ExecutionStatus,
    GeneratedExecutionOutcome,
)
from runtime.graph.state import CommerceGraphState
from runtime.handlers import CommandHandler

logger = logging.getLogger(__name__)


class ExecuteNode:
    def __init__(
        self,
        command_handler: CommandHandler,
    ) -> None:
        self._command_handler = command_handler

    async def __call__(
        self,
        state: CommerceGraphState,
    ) -> dict[str, Any]:

        print("===== Execute Node Called =====")

        if state.planner_response is None:
            raise ValueError("Planner response is required before execution.")

        session = state.session or CommerceSession()
        try:
            result = await self._command_handler.handle(
                state.planner_response.command,
                session,
            )
        except Exception:
            logger.exception("Command execution failed.")
            return {
                "execution_outcome": GeneratedExecutionOutcome(
                    status=ExecutionStatus.FAILURE,
                    fragments=(
                        ApprovedResponseFragment(
                            id="execution-failure",
                            text=(
                                "Sorry, I couldn't complete that request. "
                                "Please try again."
                            ),
                        ),
                    ),
                ),
                "session": session,
            }

        print("===== Execute Node Result =====")
        print(result)
        print("=============================================")

        return {
            "execution_outcome": result.outcome,
            "session": result.session,
        }

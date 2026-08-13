import logging
from typing import Any

from commerce.models import CommerceSession, CustomerOnboardingState, OnboardingStage
from runtime.capabilities import CapabilityName, ExecutionContext
from runtime.commands import ExecuteCapabilityCommand
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

        if state.planner_response is None:
            raise ValueError("Planner response is required before execution.")

        session = state.session or CommerceSession()
        context = state.customer_context
        if context is None:
            context = ExecutionContext(conversation_id=state.conversation_id)
        try:
            result = await self._command_handler.handle(
                state.planner_response.command,
                session,
                ExecutionContext(
                    **context.model_dump(),
                    profile=state.customer_profile_projection,
                ),
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

        result_session = result.session
        command = state.planner_response.command
        onboarding_names = {
            CapabilityName.START_CUSTOMER_ONBOARDING.value,
            CapabilityName.COLLECT_CUSTOMER_ONBOARDING_DETAILS.value,
            CapabilityName.CONFIRM_CUSTOMER_ONBOARDING.value,
            CapabilityName.SKIP_CUSTOMER_ONBOARDING.value,
            CapabilityName.GREETING.value,
        }
        if (
            isinstance(command, ExecuteCapabilityCommand)
            and command.capability not in onboarding_names
            and context.channel_customer_id is not None
            and not state.customer_profile_projection.onboarding_completed
            and result_session.customer_onboarding.stage
            in {OnboardingStage.NOT_STARTED, OnboardingStage.COLLECTING_DETAILS}
        ):
            result_session = result_session.model_copy(
                update={
                    "customer_onboarding": CustomerOnboardingState(
                        stage=OnboardingStage.SKIPPED
                    )
                }
            )

        return {
            "execution_outcome": result.outcome,
            "session": result_session,
        }

import logging
from datetime import timedelta
from typing import Any

from channels.models import MessageKind
from commerce.models import CommerceSession, CustomerEntryKind, OnboardingStage
from runtime.capabilities import CapabilityName, ExecutionContext
from runtime.commands import ExecuteCapabilityCommand
from runtime.contracts import (
    ApprovedResponseFragment,
    ExecutionStatus,
    GeneratedExecutionOutcome,
)
from runtime.customer_journey import (
    continuation_command,
    defer_command,
    with_deferred_intent,
)
from runtime.graph.state import CommerceGraphState
from runtime.handlers import CommandHandler
from runtime.observability import CustomerJourneyObserver, NullCustomerJourneyObserver

logger = logging.getLogger(__name__)


class ExecuteNode:
    def __init__(
        self,
        command_handler: CommandHandler,
        deferred_intent_ttl: timedelta = timedelta(minutes=15),
        observer: CustomerJourneyObserver | None = None,
    ) -> None:
        self._command_handler = command_handler
        self._deferred_intent_ttl = deferred_intent_ttl
        self._observer = observer or NullCustomerJourneyObserver()

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
        command = state.planner_response.command
        if (
            context.inbound_message is not None
            and context.inbound_message.message_kind is MessageKind.LOCATION
        ):
            command = ExecuteCapabilityCommand(
                capability=CapabilityName.SUBMIT_DELIVERY_LOCATION.value,
                arguments={},
            )
        stable_incomplete = (
            context.channel_customer_id is not None
            and not state.customer_profile_projection.onboarding_completed
        )
        onboarding_names = {
            CapabilityName.START_CUSTOMER_ONBOARDING.value,
            CapabilityName.COLLECT_CUSTOMER_ONBOARDING_DETAILS.value,
            CapabilityName.CONFIRM_CUSTOMER_ONBOARDING.value,
            CapabilityName.SKIP_CUSTOMER_ONBOARDING.value,
            CapabilityName.REQUEST_DELIVERY_LOCATION.value,
            CapabilityName.SUBMIT_DELIVERY_LOCATION.value,
            CapabilityName.COLLECT_DELIVERY_ADDRESS_DETAILS.value,
        }
        if (
            state.customer_profile_projection.onboarding_completed
            and isinstance(command, ExecuteCapabilityCommand)
            and command.capability
            in {
                CapabilityName.GREETING.value,
                CapabilityName.START_CUSTOMER_ONBOARDING.value,
            }
        ):
            command = ExecuteCapabilityCommand(
                capability=CapabilityName.START_CUSTOMER_SHOPPING.value,
                arguments={},
            )
            self._observer.journey_entry("returning", "categories")
        if (
            stable_incomplete
            and isinstance(command, ExecuteCapabilityCommand)
            and command.capability not in onboarding_names
            and session.customer_onboarding.stage is not OnboardingStage.SKIPPED
        ):
            session = with_deferred_intent(
                session, defer_command(command, context.request_id)
            )
            command = ExecuteCapabilityCommand(
                capability=(
                    CapabilityName.COLLECT_CUSTOMER_ONBOARDING_DETAILS.value
                    if session.customer_onboarding.stage
                    in {
                        OnboardingStage.COLLECTING_DETAILS,
                        OnboardingStage.REVIEWING_DETAILS,
                    }
                    else CapabilityName.START_CUSTOMER_ONBOARDING.value
                ),
                arguments={},
            )
            self._observer.journey_entry("first_time", "onboarding")
        try:
            result = await self._command_handler.handle(
                command,
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
        if (
            isinstance(command, ExecuteCapabilityCommand)
            and command.capability == CapabilityName.CONFIRM_CUSTOMER_ONBOARDING.value
            and result.outcome.status is ExecutionStatus.SUCCESS
        ):
            intent = result_session.deferred_customer_intent
            continuation = continuation_command(intent, ttl=self._deferred_intent_ttl)
            continuation_context = ExecutionContext(
                **context.model_dump(exclude={"profile", "request_id"}),
                request_id=(
                    intent.source_request_id
                    if intent is not None
                    else context.request_id
                ),
                profile=state.customer_profile_projection.model_copy(
                    update={
                        "profile_available": True,
                        "onboarding_completed": True,
                        "entry_kind": CustomerEntryKind.JUST_ONBOARDED,
                    }
                ),
            )
            try:
                continued = await self._command_handler.handle(
                    continuation, result_session, continuation_context
                )
            except Exception:
                logger.exception("Post-onboarding continuation failed.")
                continued = result.model_copy(
                    update={
                        "session": result_session,
                        "outcome": GeneratedExecutionOutcome(
                            status=ExecutionStatus.FAILURE,
                            fragments=(
                                ApprovedResponseFragment(
                                    id="customer-onboarding-continuation-unavailable",
                                    text="Your profile was saved, but the shopping request could not be continued temporarily.",
                                ),
                            ),
                        ),
                    }
                )
            terminal = continued.outcome.status is not ExecutionStatus.FAILURE
            self._observer.onboarding_continuation(
                intent.kind.value if intent is not None else "NONE",
                continued.outcome.status.value,
            )
            result_session = continued.session.model_copy(
                update={"deferred_customer_intent": None if terminal else intent}
            )
            if isinstance(result.outcome, GeneratedExecutionOutcome) and isinstance(
                continued.outcome, GeneratedExecutionOutcome
            ):
                result = result.model_copy(
                    update={
                        "session": result_session,
                        "outcome": continued.outcome.model_copy(
                            update={
                                "fragments": result.outcome.fragments
                                + continued.outcome.fragments,
                                "protected_values": result.outcome.protected_values
                                + continued.outcome.protected_values,
                            }
                        ),
                    }
                )

        return {
            "execution_outcome": result.outcome,
            "session": result_session,
        }

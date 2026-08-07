from __future__ import annotations

from runtime.commands import (
    ExecuteCapabilityCommand,
    PlannerCommand,
    RespondCommand,
    WaitCommand,
)

from .decision import (
    DecisionType,
    PlannerDecision,
)


class PlannerDecisionMapper:

    @staticmethod
    def to_command(
        decision: PlannerDecision,
    ) -> PlannerCommand:

        if decision.type == DecisionType.RESPOND:

            if decision.message is None:
                raise ValueError(
                    "PlannerDecision.message is required for RESPOND."
                )

            return RespondCommand(
                message=decision.message,
            )

        if decision.type == DecisionType.EXECUTE_CAPABILITY:

            if decision.capability is None:
                raise ValueError(
                    "PlannerDecision.capability is required for EXECUTE_CAPABILITY."
            )

            return ExecuteCapabilityCommand(
                capability=decision.capability,
                arguments=decision.arguments,
            )

        if decision.type == DecisionType.WAIT:
            
            if decision.capability is None:
                raise ValueError(
                    "PlannerDecision.capability is required for WAIT."
            )
            
            return WaitCommand(
                reason=decision.reason or ""
            )

        raise ValueError("Unknown decision type.")
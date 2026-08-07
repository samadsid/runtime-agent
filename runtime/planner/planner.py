from __future__ import annotations

from commerce.models import CommerceSession
from runtime.contracts import Message
from runtime.llm import LLMProvider
from runtime.planner.decision import PlannerDecision
from runtime.planner.mapper import PlannerDecisionMapper
from runtime.planner.response import PlannerResponse
from runtime.prompts.planner import PlannerPromptBuilder


class Planner:
    """
    The Planner orchestrates the reasoning process.

    It does not contain prompt logic or business logic.
    It simply coordinates the components responsible
    for those concerns.
    """

    def __init__(
        self,
        prompt_builder: PlannerPromptBuilder,
        llm_provider: LLMProvider,
    ) -> None:

        self._prompt_builder = prompt_builder
        self._llm_provider = llm_provider

    async def plan(
        self,
        messages: list[Message],
        session: CommerceSession,
    ) -> PlannerResponse:

        print("[Planner] Building prompt for conversation state...")
        request = self._prompt_builder.build(
            messages,
            session,
        )

        decision = await self._llm_provider.invoke(
            request=request,
            response_model=PlannerDecision,
        )

        print(f"[Planner] decision: {decision}")
        command = PlannerDecisionMapper.to_command(decision)

        print(f"[Planner] Mapped command: {command}")
        return PlannerResponse(command=command)

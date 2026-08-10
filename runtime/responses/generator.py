from __future__ import annotations

import logging

from runtime.contracts import (
    FixedExecutionOutcome,
    GeneratedExecutionOutcome,
    ResponseFragmentKind,
)
from runtime.llm import LLMProvider
from runtime.prompts.response import ResponsePromptBuilder

from .models import ResponseComposition, ResponseLayout

logger = logging.getLogger(__name__)


class ResponseGenerator:
    def __init__(
        self,
        prompt_builder: ResponsePromptBuilder,
        llm_provider: LLMProvider,
    ) -> None:
        self._prompt_builder = prompt_builder
        self._llm_provider = llm_provider

    async def generate(
        self,
        outcome: FixedExecutionOutcome | GeneratedExecutionOutcome,
        customer_message: str,
    ) -> str:
        if isinstance(outcome, FixedExecutionOutcome):
            return outcome.message

        composition = await self._compose(outcome, customer_message)
        return composition.message

    async def _compose(
        self,
        outcome: GeneratedExecutionOutcome,
        customer_message: str,
    ) -> ResponseComposition:
        try:
            prompt = self._prompt_builder.build(outcome, customer_message)
            composition = await self._llm_provider.invoke(
                request=prompt,
                response_model=ResponseComposition,
            )
            self._validate_composition(outcome, composition)
            return composition
        except Exception:
            logger.exception(
                "Response composition failed; using deterministic fallback."
            )
            return self._fallback_composition(outcome)

    @staticmethod
    def _validate_composition(
        outcome: GeneratedExecutionOutcome,
        composition: ResponseComposition,
    ) -> None:
        approved_fragment_ids = tuple(fragment.id for fragment in outcome.fragments)
        if composition.fragment_ids != approved_fragment_ids:
            raise ValueError(
                "Response composition must reference every approved fragment in order."
            )

        approved_follow_up_id = (
            outcome.follow_up.id if outcome.follow_up is not None else None
        )
        if composition.follow_up_id != approved_follow_up_id:
            raise ValueError("Response composition contains an invalid follow-up ID.")

        missing_values = tuple(
            value
            for value in outcome.protected_values
            if value not in composition.message
        )
        if missing_values:
            raise ValueError("Response composition altered protected values.")

    @staticmethod
    def _fallback_composition(
        outcome: GeneratedExecutionOutcome,
    ) -> ResponseComposition:
        layout = (
            ResponseLayout.LIST
            if any(
                fragment.kind == ResponseFragmentKind.ITEM
                for fragment in outcome.fragments
            )
            else ResponseLayout.PARAGRAPH
        )
        return ResponseComposition(
            layout=layout,
            fragment_ids=tuple(fragment.id for fragment in outcome.fragments),
            follow_up_id=(
                outcome.follow_up.id if outcome.follow_up is not None else None
            ),
            message=ResponseGenerator._render_approved_fallback(outcome, layout),
        )

    @staticmethod
    def _render_approved_fallback(
        outcome: GeneratedExecutionOutcome,
        layout: ResponseLayout,
    ) -> str:
        if layout == ResponseLayout.LIST:
            body = "\n".join(fragment.text for fragment in outcome.fragments)
        else:
            body = " ".join(fragment.text for fragment in outcome.fragments)

        parts = [body] if body else []
        if outcome.follow_up is not None:
            parts.append(outcome.follow_up.question)
            parts.extend(option.label for option in outcome.follow_up.options)

        return "\n".join(parts)

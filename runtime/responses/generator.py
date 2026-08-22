from __future__ import annotations

import logging

from runtime.contracts import (
    FixedExecutionOutcome,
    GeneratedExecutionOutcome,
    ResponseLayout,
)
from runtime.llm import LLMProvider
from runtime.observability import NullResponseObserver, ResponseObserver
from runtime.prompts.response import ResponsePromptBuilder

from .formatter import WhatsAppFormattingError, WhatsAppResponseFormatter
from .models import ResponseComposition

logger = logging.getLogger(__name__)


class ResponseGenerator:
    def __init__(
        self,
        prompt_builder: ResponsePromptBuilder,
        llm_provider: LLMProvider,
        observer: ResponseObserver | None = None,
    ) -> None:
        self._prompt_builder = prompt_builder
        self._llm_provider = llm_provider
        self._observer = observer or NullResponseObserver()
        self._formatter = WhatsAppResponseFormatter()

    async def generate(
        self,
        outcome: FixedExecutionOutcome | GeneratedExecutionOutcome,
        customer_message: str,
    ) -> str:
        if isinstance(outcome, FixedExecutionOutcome):
            decorated = self._formatter.apply_heading_emoji(
                outcome.message, outcome.heading_emoji
            )
            message, changed = self._formatter.normalize(decorated)
            self._formatter.validate_structure(message)
            self._observer.normalization(changed)
            self._observer.rendered(outcome.layout.value, "fixed")
            return message

        safe_outcome = self._formatter.sanitize_outcome(outcome)
        composition = await self._compose(safe_outcome, customer_message)
        decorated = self._formatter.apply_heading_emoji(
            composition.message, safe_outcome.heading_emoji
        )
        message, changed = self._formatter.normalize(decorated)
        self._formatter.validate_structure(message, safe_outcome.protected_values)
        self._observer.normalization(changed)
        return message

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
            layout = self._formatter.resolve_layout(outcome)
            self._validate_composition(outcome, composition, layout)
            self._observer.rendered(layout.value, "generated")
            return composition
        except Exception as error:
            category = (
                str(error)
                if isinstance(error, (ValueError, WhatsAppFormattingError))
                else "provider_failure"
            )
            self._observer.validation_failure(category[:64])
            logger.exception(
                "Response composition failed; using deterministic fallback."
            )
            fallback = self._fallback_composition(outcome)
            self._observer.rendered(fallback.layout.value, "fallback")
            return fallback

    @staticmethod
    def _validate_composition(
        outcome: GeneratedExecutionOutcome,
        composition: ResponseComposition,
        layout: ResponseLayout,
    ) -> None:
        if composition.layout is not layout:
            raise ValueError("invalid_layout")
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
        option_labels = (
            tuple(option.label for option in outcome.follow_up.options)
            if outcome.follow_up is not None
            else ()
        )
        option_positions: list[int] = []
        for label in option_labels:
            if composition.message.count(label) != 1:
                raise ValueError("invalid_options")
            option_positions.append(composition.message.index(label))
        if option_positions != sorted(option_positions):
            raise ValueError("invalid_option_order")
        WhatsAppResponseFormatter.validate_structure(
            composition.message, outcome.protected_values
        )
        question_count = WhatsAppResponseFormatter.question_count(composition.message)
        if outcome.follow_up is not None:
            if question_count > 1:
                raise ValueError("multiple_questions")
            if option_positions and max(option_positions) > max(
                composition.message.rfind(mark) for mark in ("?", "؟", "？")
            ):
                raise ValueError("question_not_last")
        elif question_count:
            raise ValueError("unapproved_question")
        if "\n\n\n" in composition.message:
            raise ValueError("Response composition contains unstable section spacing.")

    @staticmethod
    def _fallback_composition(
        outcome: GeneratedExecutionOutcome,
    ) -> ResponseComposition:
        layout = WhatsAppResponseFormatter.resolve_layout(outcome)
        return ResponseComposition(
            layout=layout,
            fragment_ids=tuple(fragment.id for fragment in outcome.fragments),
            follow_up_id=(
                outcome.follow_up.id if outcome.follow_up is not None else None
            ),
            message=WhatsAppResponseFormatter.render_fallback(outcome, layout),
        )

    @staticmethod
    def _render_approved_fallback(
        outcome: GeneratedExecutionOutcome, layout: ResponseLayout
    ) -> str:
        """Compatibility entry point for focused renderer tests."""
        return WhatsAppResponseFormatter.render_fallback(outcome, layout)

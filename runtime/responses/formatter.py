from __future__ import annotations

import re

from runtime.contracts import (
    ApprovedOption,
    ApprovedResponseFragment,
    FollowUpRequest,
    GeneratedExecutionOutcome,
    ResponseFragmentKind,
    ResponseIcon,
    ResponseLayout,
)

_NUMBERED_LINE = re.compile(r"^\s*\d+\.\s+", re.MULTILINE)
_QUESTION_MARKS = ("?", "؟", "？")


class WhatsAppFormattingError(ValueError):
    pass


class WhatsAppResponseFormatter:
    """Deterministic, presentation-only WhatsApp text boundary."""

    @staticmethod
    def sanitize_outcome(outcome: GeneratedExecutionOutcome) -> GeneratedExecutionOutcome:
        replacements = {
            value: WhatsAppResponseFormatter._neutralize_value(value)
            for value in outcome.protected_values
        }
        replacements = {
            source: safe for source, safe in replacements.items() if source != safe
        }
        if not replacements:
            return outcome

        def replace(text: str) -> str:
            for source in sorted(replacements, key=len, reverse=True):
                text = text.replace(source, replacements[source])
            return text

        follow_up = outcome.follow_up
        if follow_up is not None:
            follow_up = FollowUpRequest(
                id=follow_up.id,
                question=replace(follow_up.question),
                options=tuple(
                    ApprovedOption(id=option.id, label=replace(option.label))
                    for option in follow_up.options
                ),
            )
        return outcome.model_copy(
            update={
                "fragments": tuple(
                    ApprovedResponseFragment(
                        id=fragment.id,
                        text=replace(fragment.text),
                        kind=fragment.kind,
                    )
                    for fragment in outcome.fragments
                ),
                "follow_up": follow_up,
                "protected_values": tuple(replace(value) for value in outcome.protected_values),
            }
        )

    @staticmethod
    def _neutralize_value(value: str) -> str:
        if re.fullmatch(r"\*+\d{1,4}", value):
            return value
        word_joiner = "\u2060"
        return "".join(
            character + word_joiner if character in "*_~`" else character
            for character in value
        )

    @staticmethod
    def resolve_layout(outcome: GeneratedExecutionOutcome) -> ResponseLayout:
        if outcome.layout is None:  # Defensive compatibility for unvalidated callers.
            raise WhatsAppFormattingError("missing_layout")
        return outcome.layout

    @staticmethod
    def normalize(message: str) -> tuple[str, bool]:
        original = message
        lines = message.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        normalized: list[str] = []
        blank = False
        for raw_line in lines:
            line = raw_line.rstrip()
            if not line.strip():
                if normalized and not blank:
                    normalized.append("")
                blank = True
                continue
            normalized.append(line)
            blank = False
        while normalized and not normalized[-1]:
            normalized.pop()
        result = "\n".join(normalized)
        if not result:
            raise WhatsAppFormattingError("empty_message")
        return result, result != original

    @staticmethod
    def apply_heading_emoji(message: str, icon: ResponseIcon | None) -> str:
        if icon is None:
            return message
        stripped = message.lstrip()
        if stripped.startswith(icon.value) or stripped.startswith(f"*{icon.value}"):
            return message
        leading = message[: len(message) - len(stripped)]
        return f"{leading}{icon.value} {stripped}"

    @staticmethod
    def validate_structure(message: str, protected_values: tuple[str, ...] = ()) -> None:
        if "```" in message:
            raise WhatsAppFormattingError("fenced_code")
        if re.search(r"(?m)^\s*#{1,6}\s", message):
            raise WhatsAppFormattingError("markdown_heading")
        if re.search(r"<\/?[A-Za-z][^>]*>", message):
            raise WhatsAppFormattingError("html")
        if re.search(r"(?m)^\s*\|.*\|\s*$", message):
            raise WhatsAppFormattingError("markdown_table")
        markup_only = message
        for value in sorted(set(protected_values), key=len, reverse=True):
            markup_only = markup_only.replace(value, "")
        if markup_only.count("*") % 2:
            raise WhatsAppFormattingError("unbalanced_bold")
        if markup_only.count("_") % 2:
            raise WhatsAppFormattingError("unbalanced_italic")

    @staticmethod
    def question_count(message: str) -> int:
        return sum(message.count(mark) for mark in _QUESTION_MARKS)

    @staticmethod
    def render_fallback(
        outcome: GeneratedExecutionOutcome, layout: ResponseLayout
    ) -> str:
        blocks: list[str] = []
        current_lines: list[str] = []

        def flush_lines() -> None:
            if current_lines:
                blocks.append("\n".join(current_lines))
                current_lines.clear()

        for fragment in outcome.fragments:
            text = fragment.text.strip()
            if fragment.kind is ResponseFragmentKind.SECTION:
                flush_lines()
                blocks.append(f"*{text.strip('*')}*")
            elif fragment.kind is ResponseFragmentKind.TOTAL:
                flush_lines()
                label, separator, value = text.partition(":")
                blocks.append(
                    f"*{label.strip('*')}:*{value}" if separator else f"*{text.strip('*')}*"
                )
            elif fragment.kind is ResponseFragmentKind.FIELD:
                label, separator, value = text.partition(":")
                current_lines.append(
                    f"*{label.strip('*')}:*{value}" if separator else text
                )
            elif fragment.kind is ResponseFragmentKind.ITEM:
                if layout is ResponseLayout.INFORMATIONAL_LIST and not text.startswith("•"):
                    text = f"• {text}"
                current_lines.append(text)
            elif fragment.kind is ResponseFragmentKind.BULLET:
                current_lines.append(text if text.startswith("•") else f"• {text}")
            else:
                current_lines.append(text)
        flush_lines()

        if outcome.follow_up is not None:
            if outcome.follow_up.options:
                blocks.append("\n".join(option.label for option in outcome.follow_up.options))
            blocks.append(outcome.follow_up.question)
        return "\n\n".join(block for block in blocks if block)

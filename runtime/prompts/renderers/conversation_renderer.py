from __future__ import annotations

from runtime.contracts import Message


class ConversationRenderer:
    """
    Converts a ConversationState into a text representation
    suitable for inclusion in prompts.
    """

    def render(
        self,
        messages: list[Message],
    ) -> str:

        if not messages:
            return "No conversation yet."

        lines: list[str] = []

        for message in messages:
            lines.append(
                f"{message.role.value.upper()}: {message.content}"
            )

        return "\n".join(lines)
from __future__ import annotations


class PromptComposer:
    """
    Composes multiple prompt sections into
    a single prompt.
    """

    def compose(
        self,
        *sections: str,
    ) -> str:

        cleaned = [
            section.strip()
            for section in sections
            if section.strip()
        ]

        return "\n\n".join(cleaned)
from __future__ import annotations

from runtime.capabilities import CapabilityRegistry


class CapabilityRenderer:

    def render(
        self,
        registry: CapabilityRegistry,
    ) -> str:

        lines: list[str] = []

        for capability in registry.list():
            metadata = capability.metadata

            lines.append(
                f"- {metadata.name}\n"
                f"  Description: {metadata.description}"
            )

        return "\n\n".join(lines)
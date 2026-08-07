from __future__ import annotations

from runtime.capabilities import Capability


class CapabilityRegistry:
    """
    Stores and manages all available capabilities.
    """

    def __init__(self) -> None:
        self._capabilities: dict[str, Capability] = {}

    def register(self, capability: Capability) -> None:
        """
        Register a capability.
        """

        name = capability.metadata.name

        if name in self._capabilities:
            raise ValueError(
                f"Capability '{name}' is already registered."
            )

        self._capabilities[name] = capability

    def get(self, name: str) -> Capability:
        """
        Returns a capability by name.
        """

        if name not in self._capabilities:
            raise KeyError(
                f"Capability '{name}' is not registered."
            )

        return self._capabilities[name]

    def has(self, name: str) -> bool:
        """
        Checks whether a capability exists.
        """

        return name in self._capabilities

    def list(self) -> list[Capability]:
        """
        Returns all registered capabilities.
        """

        return list(self._capabilities.values())
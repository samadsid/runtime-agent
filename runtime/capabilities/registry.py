from __future__ import annotations

from collections.abc import Iterable
from typing import Generic, TypeVar

from runtime.capabilities.capability import Capability
from runtime.capabilities.exceptions import (
    DuplicateCapabilityError,
    UnknownCapabilityError,
)

SessionT = TypeVar("SessionT")


class CapabilityRegistry(Generic[SessionT]):
    """
    Immutable registry of application capabilities.

    The registry is constructed once during application startup
    and is used at runtime to resolve capabilities by name.
    """

    def __init__(
        self,
        capabilities: Iterable[Capability[SessionT]],
    ) -> None:

        self._capabilities: dict[str, Capability[SessionT]] = {}

        for capability in capabilities:
            name = capability.metadata.name

            if name in self._capabilities:
                raise DuplicateCapabilityError(
                    f"Capability '{name}' is already registered."
                )

            self._capabilities[name] = capability

    def get(
        self,
        name: str,
    ) -> Capability[SessionT]:

        try:
            return self._capabilities[name]
        except KeyError as exc:
            raise UnknownCapabilityError(
                f"Capability '{name}' is not registered."
            ) from exc

    def list(
        self,
    ) -> tuple[Capability[SessionT], ...]:
        return tuple(self._capabilities.values())

    def __contains__(
        self,
        name: str,
    ) -> bool:

        return name in self._capabilities

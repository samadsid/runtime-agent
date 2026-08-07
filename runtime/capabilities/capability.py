from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from .input import CapabilityInput
from .metadata import CapabilityMetadata
from .output import CapabilityOutput

SessionT = TypeVar("SessionT")


class Capability(ABC, Generic[SessionT]):
    @property
    @abstractmethod
    def metadata(self) -> CapabilityMetadata:
        """
        Returns capability metadata.
        """
        raise NotImplementedError

    @abstractmethod
    async def execute(
        self,
        input: CapabilityInput[SessionT],
    ) -> CapabilityOutput[SessionT]:
        """
        Executes the capability.
        """
        raise NotImplementedError

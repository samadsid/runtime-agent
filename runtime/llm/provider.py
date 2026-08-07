from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

from .request import LLMRequest

T = TypeVar("T", bound=BaseModel)


class LLMProvider(ABC):

    @abstractmethod
    async def invoke(
        self,
        request: LLMRequest,
        response_model: type[T],
    ) -> T:
        raise NotImplementedError
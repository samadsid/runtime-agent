from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from runtime.llm import LLMRequest


class PromptBuilder(ABC):
    @abstractmethod
    def build(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> LLMRequest:
        raise NotImplementedError

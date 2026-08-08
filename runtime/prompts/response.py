from __future__ import annotations

from runtime.contracts import GeneratedExecutionOutcome, Message, MessageRole
from runtime.llm import LLMRequest

from .builder import PromptBuilder
from .composer import PromptComposer
from .loader import PromptLoader


class ResponsePromptBuilder(PromptBuilder):
    def __init__(
        self,
        loader: PromptLoader,
        composer: PromptComposer,
    ) -> None:
        self._loader = loader
        self._composer = composer

    def build(
        self,
        outcome: GeneratedExecutionOutcome,
        customer_message: str,
    ) -> LLMRequest:
        system_prompt = self._composer.compose(
            self._loader.load("response-system.md"),
            self._loader.load("response-rules.md"),
        )
        response_prompt = self._loader.load("response.md").replace(
            "{{execution_outcome}}",
            outcome.model_dump_json(indent=2),
        )
        response_prompt = response_prompt.replace(
            "{{customer_message}}",
            customer_message,
        )
        return LLMRequest(
            messages=[
                Message(role=MessageRole.SYSTEM, content=system_prompt),
                Message(role=MessageRole.USER, content=response_prompt),
            ],
            temperature=0.0,
        )

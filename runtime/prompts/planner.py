from __future__ import annotations

from commerce.models import CommerceSession
from runtime.capabilities import CapabilityRegistry
from runtime.contracts import (
    Message,
    MessageRole,
)
from runtime.llm import LLMRequest

from .builder import PromptBuilder
from .composer import PromptComposer
from .loader import PromptLoader
from .renderers import (
    CapabilityRenderer,
    CommerceSessionRenderer,
    ConversationRenderer,
)


class PlannerPromptBuilder(PromptBuilder):
    def __init__(
        self,
        loader: PromptLoader,
        composer: PromptComposer,
        conversation_renderer: ConversationRenderer,
        commerce_session_renderer: CommerceSessionRenderer,
        capability_renderer: CapabilityRenderer,
        capability_registry: CapabilityRegistry[CommerceSession],
    ) -> None:

        self._loader = loader
        self._composer = composer
        self._converstation_renderer = conversation_renderer
        self._commerce_session_renderer = commerce_session_renderer
        self._capability_renderer = capability_renderer
        self._capability_registry = capability_registry

    def build(
        self,
        messages: list[Message],
        session: CommerceSession,
    ) -> LLMRequest:

        commerce_prompt = self._loader.load("commerce.md").replace(
            "{{capabilities}}",
            self._capability_renderer.render(self._capability_registry),
        )

        system_prompt = self._composer.compose(
            self._loader.load("system.md"),
            self._loader.load("rules.md"),
            commerce_prompt,
        )

        planner_template = self._loader.load("planner.md")

        planner_prompt = planner_template.replace(
            "{{conversation}}",
            self._converstation_renderer.render(messages),
        )
        planner_prompt = planner_prompt.replace(
            "{{commerce_session}}",
            self._commerce_session_renderer.render(session),
        )

        return LLMRequest(
            messages=[
                Message(
                    role=MessageRole.SYSTEM,
                    content=system_prompt,
                ),
                Message(
                    role=MessageRole.USER,
                    content=planner_prompt,
                ),
            ]
        )

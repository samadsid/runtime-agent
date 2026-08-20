from __future__ import annotations

from commerce.models import CommerceSession, CustomerProfileProjection, OnboardingStage
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
        profile: CustomerProfileProjection | None = None,
        customer_shared_location: bool = False,
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
        projection = profile or CustomerProfileProjection()
        planner_prompt += "\n\nCustomer profile projection:\n" + "\n".join(
            (
                f"Profile available: {projection.profile_available}",
                f"Stable trusted identity: {projection.has_stable_identity}",
                f"Onboarding completed: {projection.onboarding_completed}",
                "Pending onboarding workflow: "
                + str(
                    session.customer_onboarding.stage
                    in {
                        OnboardingStage.COLLECTING_DETAILS,
                        OnboardingStage.REVIEWING_DETAILS,
                    }
                ),
                "Pending deferred intent: "
                + str(session.deferred_customer_intent is not None),
                f"Preferred name: {projection.preferred_name or 'None.'}",
                "Missing fields: "
                + (
                    ", ".join(field.value for field in projection.missing_fields)
                    or "None."
                ),
                f"Hydration failed: {projection.hydration_failed}",
                f"Customer shared location: {customer_shared_location}",
            )
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

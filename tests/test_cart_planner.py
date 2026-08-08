from decimal import Decimal
from uuid import uuid4

import pytest

from commerce.models import CartItem, CommerceSession, Product
from commerce.services import CartService
from runtime.capabilities import CapabilityRegistry
from runtime.capabilities.add_to_cart import AddToCartCapability
from runtime.capabilities.remove_from_cart import RemoveFromCartCapability
from runtime.capabilities.view_cart import ViewCartCapability
from runtime.commands import ExecuteCapabilityCommand
from runtime.contracts import Message
from runtime.llm import LLMRequest
from runtime.planner import Planner
from runtime.planner.decision import DecisionType, PlannerDecision
from runtime.prompts import PlannerPromptBuilder, PromptComposer, PromptLoader
from runtime.prompts.renderers import (
    CapabilityRenderer,
    CommerceSessionRenderer,
    ConversationRenderer,
)


def product(name: str) -> Product:
    return Product(
        id=uuid4(),
        name=name,
        price=Decimal("10.00"),
        unit="kg",
    )


class CartRoutingProvider:
    def __init__(self) -> None:
        self.requests: list[LLMRequest] = []

    async def invoke(self, request, response_model):
        self.requests.append(request)
        prompt = request.messages[-1].content
        if "USER: 2 kg" in prompt:
            return PlannerDecision(
                type=DecisionType.EXECUTE_CAPABILITY,
                capability="add_to_cart",
                arguments={"quantity": 2},
            )
        if "USER: show my cart" in prompt:
            return PlannerDecision(
                type=DecisionType.EXECUTE_CAPABILITY,
                capability="view_cart",
            )
        if "USER: remove 1" in prompt:
            return PlannerDecision(
                type=DecisionType.EXECUTE_CAPABILITY,
                capability="remove_from_cart",
                arguments={"ordinal": 1},
            )
        raise AssertionError("Unexpected planner scenario")


def build_planner(provider: CartRoutingProvider) -> Planner:
    registry = CapabilityRegistry[CommerceSession](
        capabilities=(
            AddToCartCapability(CartService()),
            ViewCartCapability(),
            RemoveFromCartCapability(CartService()),
        )
    )
    prompt_builder = PlannerPromptBuilder(
        loader=PromptLoader(),
        composer=PromptComposer(),
        conversation_renderer=ConversationRenderer(),
        commerce_session_renderer=CommerceSessionRenderer(),
        capability_renderer=CapabilityRenderer(),
        capability_registry=registry,
    )
    return Planner(
        prompt_builder=prompt_builder,
        llm_provider=provider,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "capability", "arguments"),
    [
        ("2 kg", "add_to_cart", {"quantity": 2}),
        ("show my cart", "view_cart", {}),
        ("remove 1", "remove_from_cart", {"ordinal": 1}),
    ],
)
async def test_planner_routes_cart_intents(
    message: str,
    capability: str,
    arguments: dict[str, object],
) -> None:
    chicken = product("Chicken Breast")
    session = CommerceSession(
        recent_product_results=(chicken,),
        selected_product=chicken,
        cart_items=(CartItem(product=chicken, quantity=Decimal(1)),),
    )
    provider = CartRoutingProvider()

    response = await build_planner(provider).plan(
        [Message.user(message)],
        session,
    )

    assert isinstance(response.command, ExecuteCapabilityCommand)
    assert response.command.capability == capability
    assert response.command.arguments == arguments
    prompt = provider.requests[0].messages[-1].content
    assert "Selected product:\nChicken Breast" in prompt
    assert "Cart items:\n1. Chicken Breast — 1 kg" in prompt


def test_cart_capability_guidance_keeps_ordinal_namespaces_separate() -> None:
    commerce_prompt = PromptLoader().load("commerce.md")
    rules_prompt = PromptLoader().load("rules.md")

    assert "add_to_cart" in commerce_prompt
    assert "view_cart" in commerce_prompt
    assert "remove_from_cart" in commerce_prompt
    assert "Never interpret a cart ordinal" in commerce_prompt
    assert "separate namespaces" in rules_prompt

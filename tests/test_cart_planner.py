from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from commerce.models import CartItem, CommerceSession, PendingCartClear, Product
from commerce.services import CartService
from runtime.capabilities import CapabilityRegistry
from runtime.capabilities.add_to_cart import AddToCartCapability
from runtime.capabilities.clear_cart import ClearCartCapability
from runtime.capabilities.remove_from_cart import RemoveFromCartCapability
from runtime.capabilities.update_cart_item_quantity import (
    UpdateCartItemQuantityCapability,
)
from runtime.capabilities.view_cart import ViewCartCapability
from runtime.commands import ExecuteCapabilityCommand, RespondCommand
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
from tests.fakes import InMemoryCartRepository


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
        if "USER: Chicken Breast 5 kg kar do" in prompt:
            return PlannerDecision(
                type=DecisionType.EXECUTE_CAPABILITY,
                capability="update_cart_item_quantity",
                arguments={"ordinal": 1, "quantity": 5},
            )
        if "USER: isko 2 kg kar do" in prompt:
            return PlannerDecision(
                type=DecisionType.EXECUTE_CAPABILITY,
                capability="update_cart_item_quantity",
                arguments={"quantity": 2},
            )
        if "USER: clear my cart" in prompt:
            return PlannerDecision(
                type=DecisionType.EXECUTE_CAPABILITY,
                capability="clear_cart",
                arguments={"confirmed": False},
            )
        if "USER: yes, clear the entire cart" in prompt:
            return PlannerDecision(
                type=DecisionType.EXECUTE_CAPABILITY,
                capability="clear_cart",
                arguments={"confirmed": True},
            )
        if "USER: okay" in prompt:
            return PlannerDecision(
                type=DecisionType.RESPOND,
                message="Please explicitly confirm whether to clear the reviewed cart.",
            )
        if "USER: no, don't clear it" in prompt:
            return PlannerDecision(
                type=DecisionType.EXECUTE_CAPABILITY,
                capability="clear_cart",
                arguments={"declined": True},
            )
        raise AssertionError("Unexpected planner scenario")


def build_planner(provider: CartRoutingProvider) -> Planner:
    cart_service = CartService(InMemoryCartRepository())
    registry = CapabilityRegistry[CommerceSession](
        capabilities=(
            AddToCartCapability(cart_service),
            ViewCartCapability(cart_service),
            RemoveFromCartCapability(cart_service),
            UpdateCartItemQuantityCapability(cart_service),
            ClearCartCapability(cart_service),
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
        (
            "Chicken Breast 5 kg kar do",
            "update_cart_item_quantity",
            {"ordinal": 1, "quantity": 5},
        ),
        ("isko 2 kg kar do", "update_cart_item_quantity", {"quantity": 2}),
        ("clear my cart", "clear_cart", {"confirmed": False}),
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

    assert "pending saved profile use is present" in rules_prompt
    assert "select saved-address ordinal 1" in rules_prompt
    assert "takes precedence over listing or selecting saved" in rules_prompt
    assert '"yes", "haan", and' in rules_prompt
    assert '"hanji"' in rules_prompt
    assert "always pass\n  `confirmed=true`" in rules_prompt
    assert "negative reply" in rules_prompt
    assert "must not list saved addresses" in rules_prompt

    assert "`confirm_saved_profile_use` requires boolean `confirmed=true`" in commerce_prompt
    assert '"no", "nahi", or' in commerce_prompt
    assert '"nhi" declines that option' in commerce_prompt

    assert "add_to_cart" in commerce_prompt
    assert "add_product_to_cart" in commerce_prompt
    assert "resolve_pending_cart_addition" in commerce_prompt
    assert "exactly one recent product result exists" in commerce_prompt
    assert "do not ask for the same quantity again" in commerce_prompt
    assert "view_cart" in commerce_prompt
    assert "remove_from_cart" in commerce_prompt
    assert "update_cart_item_quantity" in commerce_prompt
    assert "clear_cart" in commerce_prompt
    assert "exact name identifies exactly one item" in commerce_prompt
    assert "Quantity zero" in commerce_prompt
    assert "Never interpret a cart ordinal" in commerce_prompt
    assert "separate namespaces" in rules_prompt


@pytest.mark.asyncio
async def test_planner_receives_structured_pending_clear_for_confirmation() -> None:
    chicken = product("Chicken Breast")
    pending = PendingCartClear(
        cart_id=uuid4(),
        cart_version=3,
        requested_at=datetime.now(timezone.utc),
    )
    provider = CartRoutingProvider()

    response = await build_planner(provider).plan(
        [Message.user("yes, clear the entire cart")],
        CommerceSession(
            cart_items=(CartItem(product=chicken, quantity=Decimal(1)),),
            pending_cart_clear=pending,
        ),
    )

    assert isinstance(response.command, ExecuteCapabilityCommand)
    assert response.command.capability == "clear_cart"
    assert response.command.arguments == {"confirmed": True}
    prompt = provider.requests[0].messages[-1].content
    assert "Pending cart clear:\nPresent." in prompt
    assert f"Reviewed cart version: {pending.cart_version}" in prompt


@pytest.mark.asyncio
async def test_ambiguous_acknowledgement_does_not_confirm_cart_clear() -> None:
    pending = PendingCartClear(
        cart_id=uuid4(),
        cart_version=2,
        requested_at=datetime.now(timezone.utc),
    )
    provider = CartRoutingProvider()

    response = await build_planner(provider).plan(
        [Message.user("okay")],
        CommerceSession(pending_cart_clear=pending),
    )

    assert isinstance(response.command, RespondCommand)
    assert "explicitly confirm" in response.command.message


@pytest.mark.asyncio
async def test_planner_routes_explicit_cart_clear_decline() -> None:
    pending = PendingCartClear(
        cart_id=uuid4(),
        cart_version=2,
        requested_at=datetime.now(timezone.utc),
    )
    provider = CartRoutingProvider()

    response = await build_planner(provider).plan(
        [Message.user("no, don't clear it")],
        CommerceSession(pending_cart_clear=pending),
    )

    assert isinstance(response.command, ExecuteCapabilityCommand)
    assert response.command.capability == "clear_cart"
    assert response.command.arguments == {"declined": True}

from uuid import uuid4

import pytest

from commerce.models import CheckoutStage, CheckoutState, CommerceSession
from commerce.services import (
    CartService,
    NonEmptyPhoneValidationPolicy,
    OrderService,
)
from runtime.capabilities import CapabilityRegistry
from runtime.capabilities.checkout import CheckoutCapability
from runtime.capabilities.collect_delivery_details import (
    CollectDeliveryDetailsCapability,
)
from runtime.capabilities.confirm_order import ConfirmOrderCapability
from runtime.capabilities.get_order_status import GetOrderStatusCapability
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
from tests.fakes import InMemoryCartRepository, InMemoryOrderRepository


class CheckoutRoutingProvider:
    def __init__(self) -> None:
        self.requests: list[LLMRequest] = []

    async def invoke(self, request, response_model):
        self.requests.append(request)
        latest = request.messages[-1].content
        if "USER: checkout" in latest:
            return self._execute("checkout")
        if "USER: yes proceed" in latest:
            return self._execute("checkout")
        if "USER: my name is Samad" in latest:
            return self._execute(
                "collect_delivery_details", {"customer_name": "Samad"}
            )
        if "USER: Samad, 9560717170, B-68 New Zafrabad Delhi" in latest:
            return self._execute(
                "collect_delivery_details",
                {
                    "customer_name": "Samad",
                    "phone_number": "9560717170",
                    "delivery_address": "B-68 New Zafrabad Delhi",
                },
            )
        if "USER: yes, place this order" in latest:
            return self._execute("confirm_order", {"confirmed": True})
        if "USER: okay" in latest:
            return PlannerDecision(
                type=DecisionType.RESPOND,
                message="Please explicitly confirm whether to place the order.",
            )
        if "USER: where is my order" in latest:
            return self._execute("get_order_status")
        raise AssertionError("Unexpected planner scenario")

    @staticmethod
    def _execute(
        capability: str, arguments: dict[str, object] | None = None
    ) -> PlannerDecision:
        return PlannerDecision(
            type=DecisionType.EXECUTE_CAPABILITY,
            capability=capability,
            arguments=arguments or {},
        )


def build_planner(provider: CheckoutRoutingProvider) -> Planner:
    cart_repository = InMemoryCartRepository()
    order_service = OrderService(InMemoryOrderRepository(cart_repository))
    registry = CapabilityRegistry[CommerceSession](
        capabilities=(
            CheckoutCapability(CartService(cart_repository)),
            CollectDeliveryDetailsCapability(NonEmptyPhoneValidationPolicy()),
            ConfirmOrderCapability(order_service),
            GetOrderStatusCapability(order_service),
        )
    )
    return Planner(
        prompt_builder=PlannerPromptBuilder(
            loader=PromptLoader(),
            composer=PromptComposer(),
            conversation_renderer=ConversationRenderer(),
            commerce_session_renderer=CommerceSessionRenderer(),
            capability_renderer=CapabilityRenderer(),
            capability_registry=registry,
        ),
        llm_provider=provider,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "stage", "capability", "arguments"),
    [
        ("checkout", CheckoutStage.NONE, "checkout", {}),
        ("yes proceed", CheckoutStage.REVIEWING_CART, "checkout", {}),
        (
            "my name is Samad",
            CheckoutStage.COLLECTING_DETAILS,
            "collect_delivery_details",
            {"customer_name": "Samad"},
        ),
        (
            "Samad, 9560717170, B-68 New Zafrabad Delhi",
            CheckoutStage.COLLECTING_DETAILS,
            "collect_delivery_details",
            {
                "customer_name": "Samad",
                "phone_number": "9560717170",
                "delivery_address": "B-68 New Zafrabad Delhi",
            },
        ),
        (
            "yes, place this order",
            CheckoutStage.READY_TO_CONFIRM,
            "confirm_order",
            {"confirmed": True},
        ),
        (
            "where is my order",
            CheckoutStage.NONE,
            "get_order_status",
            {},
        ),
    ],
)
async def test_planner_routes_checkout_intents(
    message: str,
    stage: CheckoutStage,
    capability: str,
    arguments: dict[str, object],
) -> None:
    session = CommerceSession(
        checkout=CheckoutState(
            stage=stage,
            source_cart_id=uuid4() if stage != CheckoutStage.NONE else None,
            customer_name="Samad" if stage == CheckoutStage.READY_TO_CONFIRM else None,
            phone_number="9876543210"
            if stage == CheckoutStage.READY_TO_CONFIRM
            else None,
            delivery_address="12 Market Road"
            if stage == CheckoutStage.READY_TO_CONFIRM
            else None,
        )
    )
    provider = CheckoutRoutingProvider()

    response = await build_planner(provider).plan([Message.user(message)], session)

    assert isinstance(response.command, ExecuteCapabilityCommand)
    assert response.command.capability == capability
    assert response.command.arguments == arguments
    prompt = provider.requests[0].messages[-1].content
    assert f"Stage: {stage.value}" in prompt
    assert "9876543210" not in prompt
    assert "12 Market Road" not in prompt


@pytest.mark.asyncio
async def test_planner_does_not_confirm_ambiguous_acknowledgement() -> None:
    session = CommerceSession(
        checkout=CheckoutState(
            stage=CheckoutStage.READY_TO_CONFIRM,
            source_cart_id=uuid4(),
            customer_name="Samad",
            phone_number="9876543210",
            delivery_address="12 Market Road",
        )
    )

    response = await build_planner(CheckoutRoutingProvider()).plan(
        [Message.user("okay")], session
    )

    assert isinstance(response.command, RespondCommand)

from uuid import uuid4

import pytest

from commerce.models import CheckoutStage, CheckoutState, CommerceSession
from commerce.services import (
    CartService,
    NonEmptyPhoneValidationPolicy,
    OrderService,
)
from runtime.capabilities import CapabilityRegistry
from runtime.capabilities.abandon_checkout import AbandonCheckoutCapability
from runtime.capabilities.checkout import CheckoutCapability
from runtime.capabilities.collect_delivery_details import (
    CollectDeliveryDetailsCapability,
)
from runtime.capabilities.confirm_order import ConfirmOrderCapability
from runtime.capabilities.get_order_status import GetOrderStatusCapability
from runtime.capabilities.update_delivery_details import (
    UpdateDeliveryDetailsCapability,
)
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
        if "USER: checkout rehne do" in latest:
            return self._execute("abandon_checkout")
        if "USER: checkout" in latest:
            return self._execute("checkout")
        if "USER: yes proceed" in latest:
            return self._execute("checkout")
        if "USER: my name is Samad" in latest:
            return self._execute("collect_delivery_details", {"customer_name": "Samad"})
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
        if "USER: address change karna hai" in latest:
            return self._execute(
                "update_delivery_details", {"requested_field": "delivery_address"}
            )
        if "USER: मेरा पता बदलकर B-68 कर दो" in latest:
            return self._execute(
                "update_delivery_details", {"delivery_address": "B-68"}
            )
        if "USER: mera number 9560717170 kar do" in latest:
            return self._execute(
                "update_delivery_details", {"phone_number": "9560717170"}
            )
        if "USER: name Aman and address B-68 kar do" in latest:
            return self._execute(
                "update_delivery_details",
                {"customer_name": "Aman", "delivery_address": "B-68"},
            )
        if "USER: B-68 New Zafrabad Delhi" in latest:
            return self._execute(
                "update_delivery_details",
                {"delivery_address": "B-68 New Zafrabad Delhi"},
            )
        if "USER: cancel" in latest:
            return PlannerDecision(
                type=DecisionType.RESPOND,
                message="Do you want to stop checkout or cancel a confirmed order?",
            )
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
            UpdateDeliveryDetailsCapability(
                CartService(cart_repository), NonEmptyPhoneValidationPolicy()
            ),
            AbandonCheckoutCapability(),
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "arguments"),
    [
        ("address change karna hai", {"requested_field": "delivery_address"}),
        ("मेरा पता बदलकर B-68 कर दो", {"delivery_address": "B-68"}),
        ("mera number 9560717170 kar do", {"phone_number": "9560717170"}),
        (
            "name Aman and address B-68 kar do",
            {"customer_name": "Aman", "delivery_address": "B-68"},
        ),
    ],
)
async def test_planner_routes_multilingual_delivery_corrections(
    message: str, arguments: dict[str, object]
) -> None:
    session = CommerceSession(
        checkout=CheckoutState(
            stage=CheckoutStage.READY_TO_CONFIRM,
            source_cart_id=uuid4(),
            customer_name="Samad",
            phone_number="9876543210",
            delivery_address="Old Address",
        )
    )

    response = await build_planner(CheckoutRoutingProvider()).plan(
        [Message.user(message)], session
    )

    assert isinstance(response.command, ExecuteCapabilityCommand)
    assert response.command.capability == "update_delivery_details"
    assert response.command.arguments == arguments


@pytest.mark.asyncio
async def test_planner_uses_pending_correction_for_bare_value() -> None:
    from commerce.models import DeliveryDetailField

    session = CommerceSession(
        checkout=CheckoutState(
            stage=CheckoutStage.READY_TO_CONFIRM,
            source_cart_id=uuid4(),
            customer_name="Samad",
            phone_number="9876543210",
            delivery_address="Old Address",
            pending_delivery_correction=DeliveryDetailField.DELIVERY_ADDRESS,
        )
    )

    response = await build_planner(CheckoutRoutingProvider()).plan(
        [Message.user("B-68 New Zafrabad Delhi")], session
    )

    assert isinstance(response.command, ExecuteCapabilityCommand)
    assert response.command.capability == "update_delivery_details"
    assert response.command.arguments == {"delivery_address": "B-68 New Zafrabad Delhi"}


@pytest.mark.asyncio
async def test_planner_routes_abandonment_and_clarifies_ambiguous_cancel() -> None:
    session = CommerceSession(
        checkout=CheckoutState(
            stage=CheckoutStage.COLLECTING_DETAILS, source_cart_id=uuid4()
        )
    )
    planner = build_planner(CheckoutRoutingProvider())

    abandoned = await planner.plan([Message.user("checkout rehne do")], session)
    ambiguous = await planner.plan([Message.user("cancel")], session)

    assert isinstance(abandoned.command, ExecuteCapabilityCommand)
    assert abandoned.command.capability == "abandon_checkout"
    assert isinstance(ambiguous.command, RespondCommand)

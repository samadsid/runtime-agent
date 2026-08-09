from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from commerce.models import CommerceSession, PendingOrderCancellation
from commerce.services import OrderService
from runtime.capabilities import CapabilityRegistry
from runtime.capabilities.cancel_order import CancelOrderCapability
from runtime.capabilities.get_order_details import GetOrderDetailsCapability
from runtime.capabilities.get_order_status import GetOrderStatusCapability
from runtime.capabilities.list_orders import ListOrdersCapability
from runtime.commands import ExecuteCapabilityCommand, RespondCommand
from runtime.contracts import Message
from runtime.planner import Planner
from runtime.planner.decision import DecisionType, PlannerDecision
from runtime.prompts import PlannerPromptBuilder, PromptComposer, PromptLoader
from runtime.prompts.renderers import (
    CapabilityRenderer,
    CommerceSessionRenderer,
    ConversationRenderer,
)
from tests.test_customer_order_management import setup_orders


class CustomerOrderRoutingProvider:
    async def invoke(self, request, response_model):
        prompt = request.messages[-1].content
        if "USER: show my orders" in prompt:
            return self.execute("list_orders")
        if "USER: details of latest" in prompt:
            return self.execute("get_order_details", {"latest": True})
        if "USER: cancel latest" in prompt:
            return self.execute(
                "cancel_order", {"latest": True, "confirmed": False}
            )
        if "USER: yes, cancel this order" in prompt:
            assert "Pending order cancellation:\nPresent." in prompt
            return self.execute("cancel_order", {"confirmed": True})
        if "USER: okay" in prompt:
            return PlannerDecision(
                type=DecisionType.RESPOND,
                message="Please explicitly confirm cancellation.",
            )
        if "USER: where is my order" in prompt:
            return self.execute("get_order_status")
        raise AssertionError("Unexpected scenario")

    @staticmethod
    def execute(capability, arguments=None):
        return PlannerDecision(
            type=DecisionType.EXECUTE_CAPABILITY,
            capability=capability,
            arguments=arguments or {},
        )


def build_planner():
    _, unit_of_work, customer_service = setup_orders()

    registry = CapabilityRegistry[CommerceSession](
        (
            ListOrdersCapability(customer_service),
            GetOrderDetailsCapability(customer_service),
            CancelOrderCapability(customer_service, "support@example.com"),
            GetOrderStatusCapability(OrderService(unit_of_work.orders)),
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
        llm_provider=CustomerOrderRoutingProvider(),  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "capability", "arguments"),
    (
        ("show my orders", "list_orders", {}),
        ("details of latest", "get_order_details", {"latest": True}),
        (
            "cancel latest",
            "cancel_order",
            {"latest": True, "confirmed": False},
        ),
        ("where is my order", "get_order_status", {}),
    ),
)
async def test_planner_routes_customer_order_intents(
    message, capability, arguments
) -> None:
    response = await build_planner().plan(
        [Message.user(message)], CommerceSession()
    )

    assert isinstance(response.command, ExecuteCapabilityCommand)
    assert response.command.capability == capability
    assert response.command.arguments == arguments


@pytest.mark.asyncio
async def test_planner_only_confirms_explicit_pending_cancellation() -> None:
    pending = PendingOrderCancellation(
        order_id=uuid4(), requested_at=datetime.now(timezone.utc)
    )
    session = CommerceSession(pending_order_cancellation=pending)
    planner = build_planner()

    explicit = await planner.plan(
        [Message.user("yes, cancel this order")], session
    )
    ambiguous = await planner.plan([Message.user("okay")], session)

    assert isinstance(explicit.command, ExecuteCapabilityCommand)
    assert explicit.command.arguments == {"confirmed": True}
    assert isinstance(ambiguous.command, RespondCommand)

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from commerce.models import (
    ChannelName,
    CommerceSession,
    CustomerOnboardingState,
    CustomerProfileProjection,
    DeferredCustomerIntent,
    DeferredCustomerIntentKind,
    OnboardingStage,
)
from runtime.capabilities import ExecutionContext
from runtime.commands import ExecuteCapabilityCommand
from runtime.contracts import (
    ApprovedResponseFragment,
    CustomerChannelContext,
    ExecutionStatus,
    GeneratedExecutionOutcome,
)
from runtime.customer_journey import defer_command
from runtime.graph.nodes.execute_node import ExecuteNode
from runtime.graph.state import CommerceGraphState
from runtime.handlers.result import HandlerResult
from runtime.planner.response import PlannerResponse


def context(request_id: str = "whatsapp:wamid.original") -> CustomerChannelContext:
    return CustomerChannelContext(
        tenant_id=uuid4(),
        conversation_id=uuid4(),
        channel=ChannelName.WHATSAPP,
        channel_customer_id="+919999999999",
        request_id=request_id,
    )


def outcome(fragment_id: str) -> GeneratedExecutionOutcome:
    return GeneratedExecutionOutcome(
        status=ExecutionStatus.SUCCESS,
        fragments=(ApprovedResponseFragment(id=fragment_id, text=fragment_id),),
    )


def test_only_validated_direct_add_is_deferred() -> None:
    command = ExecuteCapabilityCommand(
        capability="add_product_to_cart",
        arguments={
            "product_query": "Chicken Breast",
            "quantity": Decimal(10),
            "stated_unit": "kg",
        },
    )

    deferred = defer_command(command, "whatsapp:wamid.1")

    assert deferred is not None
    assert deferred.kind is DeferredCustomerIntentKind.DIRECT_CART_ADD
    assert deferred.product_query == "Chicken Breast"
    assert deferred.quantity == Decimal(10)
    assert (
        defer_command(
            command.model_copy(update={"arguments": {"quantity": "NaN"}}),
            "whatsapp:wamid.1",
        )
        is None
    )


class RecordingJourneyHandler:
    def __init__(self) -> None:
        self.calls: list[
            tuple[ExecuteCapabilityCommand, CommerceSession, ExecutionContext]
        ] = []

    async def handle(self, command, session, execution_context):
        assert isinstance(command, ExecuteCapabilityCommand)
        self.calls.append((command, session, execution_context))
        if command.capability == "start_customer_onboarding":
            return HandlerResult(
                session=session.model_copy(
                    update={
                        "customer_onboarding": CustomerOnboardingState(
                            stage=OnboardingStage.COLLECTING_DETAILS
                        )
                    }
                ),
                outcome=outcome("customer-onboarding-started"),
            )
        if command.capability == "confirm_customer_onboarding":
            return HandlerResult(
                session=session.model_copy(
                    update={
                        "customer_onboarding": CustomerOnboardingState(
                            stage=OnboardingStage.COMPLETED
                        )
                    }
                ),
                outcome=outcome("customer-profile-saved"),
            )
        return HandlerResult(session=session, outcome=outcome("cart-added"))


@pytest.mark.asyncio
async def test_incomplete_stable_customer_is_onboarded_and_intent_is_preserved() -> (
    None
):
    handler = RecordingJourneyHandler()
    customer_context = context()
    state = CommerceGraphState(
        conversation_id=customer_context.conversation_id,
        customer_context=customer_context,
        customer_profile_projection=CustomerProfileProjection(),
        planner_response=PlannerResponse(
            command=ExecuteCapabilityCommand(
                capability="add_product_to_cart",
                arguments={"product_query": "Chicken", "quantity": Decimal(2)},
            )
        ),
    )

    update = await ExecuteNode(handler).__call__(state)  # type: ignore[arg-type]

    assert [call[0].capability for call in handler.calls] == [
        "start_customer_onboarding"
    ]
    deferred = update["session"].deferred_customer_intent
    assert deferred is not None
    assert deferred.source_request_id == customer_context.request_id


@pytest.mark.asyncio
async def test_confirmation_continues_direct_add_with_original_request_id() -> None:
    handler = RecordingJourneyHandler()
    customer_context = context("whatsapp:wamid.confirm")
    deferred = DeferredCustomerIntent(
        kind=DeferredCustomerIntentKind.DIRECT_CART_ADD,
        product_query="Chicken",
        quantity=Decimal(2),
        source_request_id="whatsapp:wamid.original",
        created_at=datetime.now(timezone.utc),
    )
    session = CommerceSession(
        customer_onboarding=CustomerOnboardingState(
            stage=OnboardingStage.REVIEWING_DETAILS,
            pending_customer_name="Samad",
            pending_phone_number="9999999999",
            pending_delivery_address="Delhi",
        ),
        deferred_customer_intent=deferred,
    )
    state = CommerceGraphState(
        conversation_id=customer_context.conversation_id,
        customer_context=customer_context,
        customer_profile_projection=CustomerProfileProjection(),
        session=session,
        planner_response=PlannerResponse(
            command=ExecuteCapabilityCommand(
                capability="confirm_customer_onboarding", arguments={}
            )
        ),
    )

    update = await ExecuteNode(handler).__call__(state)  # type: ignore[arg-type]

    assert [call[0].capability for call in handler.calls] == [
        "confirm_customer_onboarding",
        "add_product_to_cart",
    ]
    continuation_context = handler.calls[1][2]
    assert continuation_context.request_id == "whatsapp:wamid.original"
    assert update["session"].deferred_customer_intent is None
    assert [fragment.id for fragment in update["execution_outcome"].fragments] == [
        "customer-profile-saved",
        "cart-added",
    ]

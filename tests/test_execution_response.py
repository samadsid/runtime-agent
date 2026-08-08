from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from commerce.models import CommerceSession
from runtime.commands import RespondCommand
from runtime.contracts import (
    ApprovedOption,
    ApprovedResponseFragment,
    ExecutionStatus,
    FixedExecutionOutcome,
    FollowUpRequest,
    GeneratedExecutionOutcome,
    ResponseFragmentKind,
)
from runtime.graph.adapters import LangChainMessageAdapter
from runtime.graph.nodes import ExecuteNode, ResponseNode
from runtime.graph.state import CommerceGraphState
from runtime.planner.response import PlannerResponse
from runtime.prompts import PromptComposer, PromptLoader, ResponsePromptBuilder
from runtime.responses import ResponseComposition, ResponseGenerator, ResponseLayout


class StubLLMProvider:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.requests = []

    async def invoke(self, request, response_model):
        self.requests.append((request, response_model))
        if self.error is not None:
            raise self.error
        return self.result


def response_generator(provider: StubLLMProvider) -> ResponseGenerator:
    return ResponseGenerator(
        prompt_builder=ResponsePromptBuilder(
            loader=PromptLoader(),
            composer=PromptComposer(),
        ),
        llm_provider=provider,  # type: ignore[arg-type]
    )


def generated_outcome() -> GeneratedExecutionOutcome:
    return GeneratedExecutionOutcome(
        status=ExecutionStatus.INVALID_INPUT,
        fragments=(
            ApprovedResponseFragment(id="explanation", text="Choose a valid item."),
        ),
        follow_up=FollowUpRequest(
            id="question",
            question="Which item would you like?",
            options=(ApprovedOption(id="one", label="1. First item"),),
        ),
    )


def test_generated_outcome_requires_follow_up_for_customer_correction() -> None:
    with pytest.raises(ValidationError):
        GeneratedExecutionOutcome(
            status=ExecutionStatus.INVALID_INPUT,
            fragments=(ApprovedResponseFragment(id="error", text="Invalid."),),
        )


def test_follow_up_rejects_duplicate_option_ids() -> None:
    with pytest.raises(ValidationError):
        FollowUpRequest(
            id="question",
            question="Which item?",
            options=(
                ApprovedOption(id="same", label="First"),
                ApprovedOption(id="same", label="Second"),
            ),
        )


@pytest.mark.asyncio
async def test_generator_returns_grounded_llm_response() -> None:
    provider = StubLLMProvider(
        result=ResponseComposition(
            layout=ResponseLayout.LIST,
            fragment_ids=("explanation",),
            follow_up_id="question",
            message=(
                "Choose a valid item.\n"
                "Which item would you like?\n"
                "1. First item"
            ),
        )
    )

    message = await response_generator(provider).generate(
        generated_outcome(),
        "Show me the items",
    )

    assert message == (
        "Choose a valid item.\n"
        "Which item would you like?\n"
        "1. First item"
    )
    request, response_model = provider.requests[0]
    assert response_model is ResponseComposition
    assert request.temperature == 0.0


@pytest.mark.asyncio
async def test_generator_rejects_unapproved_ids_and_falls_back() -> None:
    provider = StubLLMProvider(
        result=ResponseComposition(
            layout=ResponseLayout.LIST,
            fragment_ids=("invented-product",),
            follow_up_id="question",
            message="An invented product is available.",
        )
    )

    message = await response_generator(provider).generate(
        generated_outcome(),
        "Show me the items",
    )

    assert "invented-product" not in message
    assert message.startswith("Choose a valid item.")
    assert message.count("Which item would you like?") == 1


@pytest.mark.asyncio
async def test_generator_uses_list_fallback_when_provider_fails() -> None:
    outcome = GeneratedExecutionOutcome(
        status=ExecutionStatus.SUCCESS,
        fragments=(
            ApprovedResponseFragment(id="heading", text="Available:"),
            ApprovedResponseFragment(
                id="item", text="1. Product", kind=ResponseFragmentKind.ITEM
            ),
        ),
    )
    provider = StubLLMProvider(error=RuntimeError("provider failed"))

    message = await response_generator(provider).generate(outcome, "Show products")

    assert message == "Available:\n1. Product"


@pytest.mark.asyncio
async def test_fixed_response_bypasses_llm() -> None:
    provider = StubLLMProvider(error=AssertionError("LLM must not be called"))
    outcome = FixedExecutionOutcome(
        status=ExecutionStatus.SUCCESS,
        message="Direct planner response.",
    )

    message = await response_generator(provider).generate(outcome, "Hello")

    assert message == "Direct planner response."
    assert provider.requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("customer_message", "llm_response"),
    [
        (
            "मुझे पहला वाला चाहिए",
            "सही आइटम चुनें। आप कौन-सा आइटम चाहते हैं? 1. First item",
        ),
        (
            "¿Quiero el primero, cuál elijo?",
            "Elige un artículo válido. ¿Cuál quieres? 1. First item",
        ),
        (
            "最初の商品が欲しいです",
            "有効な商品を選んでください。どの商品にしますか？ 1. First item",
        ),
    ],
)
async def test_generator_uses_any_customer_language_from_llm(
    customer_message: str,
    llm_response: str,
) -> None:
    provider = StubLLMProvider(
        result=ResponseComposition(
            layout=ResponseLayout.PARAGRAPH,
            fragment_ids=("explanation",),
            follow_up_id="question",
            message=llm_response,
        )
    )

    message = await response_generator(provider).generate(
        generated_outcome(),
        customer_message,
    )

    assert message == llm_response
    prompt = provider.requests[0][0].messages[-1].content
    assert customer_message in prompt


class FailingCommandHandler:
    async def handle(self, command, session):
        raise RuntimeError("secret database exception")


@pytest.mark.asyncio
async def test_execute_node_converts_internal_error_to_safe_generated_outcome() -> None:
    session = CommerceSession()
    state = CommerceGraphState(
        conversation_id=uuid4(),
        session=session,
        planner_response=PlannerResponse(
            command=RespondCommand(message="unused")
        ),
    )

    update = await ExecuteNode(FailingCommandHandler()).__call__(state)  # type: ignore[arg-type]

    assert update["session"] is session
    assert update["execution_outcome"].status == ExecutionStatus.FAILURE
    assert "secret" not in update["execution_outcome"].fragments[0].text


@pytest.mark.asyncio
async def test_response_node_emits_one_message_without_session_update() -> None:
    provider = StubLLMProvider(
        result=ResponseComposition(
            layout=ResponseLayout.PARAGRAPH,
            fragment_ids=("explanation",),
            follow_up_id="question",
            message="Choose a valid item. Which item would you like? 1. First item",
        )
    )
    state = CommerceGraphState(
        conversation_id=uuid4(),
        execution_outcome=generated_outcome(),
    )
    node = ResponseNode(
        response_generator(provider),
        LangChainMessageAdapter(),
    )

    update = await node(state)

    assert set(update) == {"messages"}
    assert len(update["messages"]) == 1
    assert update["messages"][0].content.count("Which item would you like?") == 1

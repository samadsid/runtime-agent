from decimal import Decimal
from uuid import uuid4

import pytest

from commerce.models import CommerceSession, Product
from commerce.services import CartService
from runtime.capabilities import CapabilityRegistry
from runtime.capabilities.add_to_cart import AddToCartCapability
from runtime.capabilities.greeting import GreetingCapability
from runtime.capabilities.remove_from_cart import RemoveFromCartCapability
from runtime.capabilities.search_product import SearchProductCapability
from runtime.capabilities.select_product import SelectProductCapability
from runtime.capabilities.view_cart import ViewCartCapability
from runtime.commands import ExecuteCapabilityCommand
from runtime.contracts import ConversationState
from runtime.graph import CommerceGraph
from runtime.graph.adapters import ConversationStateAdapter, LangChainMessageAdapter
from runtime.graph.memory import ConversationThread, GraphCheckpointer, MemoryManager
from runtime.handlers import (
    CommandHandler,
    ExecuteCapabilityHandler,
    RespondHandler,
    WaitHandler,
)
from runtime.planner.response import PlannerResponse


class ApprovedResponseGenerator:
    async def generate(self, outcome, customer_message: str) -> str:
        if outcome.mode == "fixed":
            return outcome.message
        parts = [fragment.text for fragment in outcome.fragments]
        if outcome.follow_up is not None:
            parts.append(outcome.follow_up.question)
        return "\n".join(parts)


class StubSearchService:
    def __init__(self, products: list[Product]) -> None:
        self.products = products

    async def search(self, query: str) -> list[Product]:
        return self.products


class ReferencePlanner:
    def __init__(self) -> None:
        self.observed_sessions: list[CommerceSession] = []

    async def plan(self, messages, session: CommerceSession) -> PlannerResponse:
        self.observed_sessions.append(session)
        latest = messages[-1].content
        if latest == "chicken":
            command = ExecuteCapabilityCommand(
                capability="search_product",
                arguments={"query": "chicken"},
            )
        elif latest == "2 kg":
            command = ExecuteCapabilityCommand(
                capability="add_to_cart",
                arguments={"quantity": 2},
            )
        elif latest == "show my cart":
            command = ExecuteCapabilityCommand(
                capability="view_cart",
            )
        elif latest == "remove 1":
            command = ExecuteCapabilityCommand(
                capability="remove_from_cart",
                arguments={"ordinal": 1},
            )
        else:
            command = ExecuteCapabilityCommand(
                capability="select_product",
                arguments={"ordinal": 1},
            )
        return PlannerResponse(command=command)


def product(name: str) -> Product:
    return Product(
        id=uuid4(),
        name=name,
        price=Decimal("10.00"),
        unit="kg",
    )


def build_graph(products: list[Product]):
    planner = ReferencePlanner()
    registry = CapabilityRegistry[CommerceSession](
        capabilities=[
            GreetingCapability(),
            SearchProductCapability(
                service=StubSearchService(products),  # type: ignore[arg-type]
            ),
            SelectProductCapability(),
            AddToCartCapability(CartService()),
            ViewCartCapability(),
            RemoveFromCartCapability(CartService()),
        ]
    )
    handler = CommandHandler[CommerceSession](
        respond_handler=RespondHandler[CommerceSession](),
        execute_capability_handler=ExecuteCapabilityHandler[CommerceSession](
            registry=registry
        ),
        wait_handler=WaitHandler[CommerceSession](),
    )
    message_adapter = LangChainMessageAdapter()
    checkpointer = GraphCheckpointer()
    graph = CommerceGraph(
        planner=planner,  # type: ignore[arg-type]
        command_handler=handler,
        memory_manager=MemoryManager(checkpointer),  # type: ignore[arg-type]
        message_adapter=message_adapter,
        response_generator=ApprovedResponseGenerator(),  # type: ignore[arg-type]
    )
    adapter = ConversationStateAdapter(message_adapter)
    return graph, adapter, planner, checkpointer


@pytest.mark.asyncio
async def test_message_only_second_invocation_restores_and_selects_first_product() -> (
    None
):
    breast = product("Chicken Breast")
    wings = product("Chicken Wings")
    graph, adapter, planner, checkpointer = build_graph([breast, wings])
    conversation_id = uuid4()

    first_conversation = ConversationState(conversation_id=conversation_id)
    first_conversation.add_user_message("chicken")
    first_state = await graph.invoke(adapter.to_graph_state(first_conversation))

    assert first_state.session is not None
    assert first_state.session.recent_product_results == (breast, wings)

    second_conversation = ConversationState(conversation_id=conversation_id)
    second_conversation.add_user_message("first one")
    inbound_state = adapter.to_graph_state(second_conversation)
    assert inbound_state.session is None

    second_state = await graph.invoke(inbound_state)

    assert planner.observed_sessions[1].recent_product_results == (breast, wings)
    assert second_state.session is not None
    assert second_state.session.selected_product == breast
    assert "session" not in ConversationState.model_fields

    restored_conversation = adapter.from_graph_state(second_state)
    assert not hasattr(restored_conversation, "session")

    config = {
        "configurable": {
            "thread_id": ConversationThread(conversation_id).id,
        }
    }
    checkpoint = await checkpointer.instance.aget_tuple(config)
    assert checkpoint is not None
    channel_values = checkpoint.checkpoint["channel_values"]
    assert channel_values["session"].selected_product == breast
    assert "planner_response" not in channel_values
    assert "execution_outcome" not in channel_values


@pytest.mark.asyncio
async def test_different_thread_does_not_receive_product_context() -> None:
    graph, adapter, planner, _ = build_graph([product("Chicken Breast")])

    first = ConversationState(conversation_id=uuid4())
    first.add_user_message("chicken")
    await graph.invoke(adapter.to_graph_state(first))

    unrelated = ConversationState(conversation_id=uuid4())
    unrelated.add_user_message("first one")
    state = await graph.invoke(adapter.to_graph_state(unrelated))

    assert planner.observed_sessions[1] == CommerceSession()
    assert state.session == CommerceSession()


@pytest.mark.asyncio
async def test_cart_state_survives_add_view_and_remove_across_turns() -> None:
    chicken = product("Chicken Breast")
    graph, adapter, planner, checkpointer = build_graph([chicken])
    conversation_id = uuid4()

    async def invoke(message: str):
        conversation = ConversationState(conversation_id=conversation_id)
        conversation.add_user_message(message)
        return await graph.invoke(adapter.to_graph_state(conversation))

    await invoke("chicken")
    await invoke("first one")
    added = await invoke("2 kg")
    viewed = await invoke("show my cart")
    removed = await invoke("remove 1")

    assert added.session is not None
    assert added.session.cart_items[0].product == chicken
    assert added.session.cart_items[0].quantity == Decimal(2)
    assert viewed.session is not None
    assert viewed.session.cart_items == added.session.cart_items
    assert removed.session is not None
    assert removed.session.cart_items == ()
    assert removed.session.selected_product == chicken
    assert planner.observed_sessions[2].selected_product == chicken

    checkpoint = await checkpointer.instance.aget_tuple(
        {"configurable": {"thread_id": ConversationThread(conversation_id).id}}
    )
    assert checkpoint is not None
    assert checkpoint.checkpoint["channel_values"]["session"].cart_items == ()

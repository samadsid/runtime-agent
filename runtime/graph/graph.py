from __future__ import annotations

from datetime import timedelta

from langgraph.graph import END, START, StateGraph

from runtime.graph.adapters import MessageAdapter
from runtime.graph.memory import ConversationThread, MemoryManager
from runtime.graph.nodes import ExecuteNode, PlannerNode, ResponseNode
from runtime.graph.state import CommerceGraphState
from runtime.handlers import CommandHandler
from runtime.observability import CustomerJourneyObserver
from runtime.planner import Planner
from runtime.responses import ResponseGenerator


class CommerceGraph:
    def __init__(
        self,
        planner: Planner,
        command_handler: CommandHandler,
        memory_manager: MemoryManager,
        message_adapter: MessageAdapter,
        response_generator: ResponseGenerator,
        deferred_intent_ttl: timedelta = timedelta(minutes=15),
        customer_journey_observer: CustomerJourneyObserver | None = None,
    ) -> None:

        self._planner_node = PlannerNode(planner, message_adapter)

        self._execute_node = ExecuteNode(
            command_handler, deferred_intent_ttl, customer_journey_observer
        )

        self._response_node = ResponseNode(response_generator, message_adapter)

        self._memory_manager = memory_manager

        graph = StateGraph(CommerceGraphState)

        graph.add_node(
            "planner",
            self._planner_node,
        )

        graph.add_node(
            "execute",
            self._execute_node,
        )

        graph.add_node(
            "response",
            self._response_node,
        )

        graph.add_edge(
            START,
            "planner",
        )

        graph.add_edge(
            "planner",
            "execute",
        )

        graph.add_edge(
            "execute",
            "response",
        )

        graph.add_edge(
            "response",
            END,
        )

        self._graph = graph.compile(
            checkpointer=self._memory_manager.checkpointer,
        )

    async def invoke(
        self,
        state: CommerceGraphState,
    ) -> CommerceGraphState:

        thread = ConversationThread(
            state.conversation_id,
        )

        result = await self._graph.ainvoke(
            state,
            config={
                "configurable": {
                    "thread_id": thread.id,
                }
            },
        )

        return CommerceGraphState.model_validate(result)

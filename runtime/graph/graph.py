from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from runtime.graph.adapters import MessageAdapter
from runtime.graph.memory import ConversationThread
from runtime.graph.nodes import ExecuteNode, PlannerNode, ResponseNode
from runtime.graph.state import CommerceGraphState
from runtime.handlers import CommandHandler
from runtime.planner import Planner
from runtime.responses import ResponseGenerator


class CommerceGraph:

    def __init__(
        self,
        planner: Planner,
        command_handler: CommandHandler,
        memory_manager: MemorySaver,
        message_adapter: MessageAdapter,
        response_generator: ResponseGenerator,
    ) -> None:
        
        self._planner_node = PlannerNode(planner, message_adapter)

        self._execute_node = ExecuteNode(command_handler)

        self._response_node = ResponseNode(response_generator, message_adapter)
        
        self._memory_manager = memory_manager
        
        graph = StateGraph(
            CommerceGraphState
        )

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

        result = await self._graph.ainvoke(state, 
            config={
            "configurable": {
                "thread_id": thread.id,
            }
            },
        )

        return CommerceGraphState.model_validate(result)

from __future__ import annotations

from langgraph.graph import END
from langgraph.graph import START
from langgraph.graph import StateGraph
from langgraph.checkpoint.memory import MemorySaver
from runtime.graph.memory import ConversationThread


from runtime.graph.state import CommerceGraphState
from runtime.planner import Planner
from runtime.handlers import CommandHandler
from runtime.graph.nodes import PlannerNode, ExecuteNode

from runtime.graph.adapters import MessageAdapter


class CommerceGraph:

    def __init__(
        self,
        planner: Planner,
        command_handler: CommandHandler,
        memory_manager: MemorySaver,
        message_adapter: MessageAdapter,
    ) -> None:
        
        self._planner_node = PlannerNode(planner, message_adapter)

        self._execute_node = ExecuteNode(command_handler, message_adapter)
        
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
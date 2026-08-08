from __future__ import annotations

from typing import Annotated
from uuid import UUID

from langchain_core.messages import BaseMessage
from langgraph.channels import UntrackedValue
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

from commerce.models import CommerceSession
from runtime.contracts import ExecutionOutcome
from runtime.planner.response import PlannerResponse


def retain_commerce_session(
    current: CommerceSession | None,
    incoming: CommerceSession | None,
) -> CommerceSession | None:
    if incoming is None:
        return current
    return incoming


class CommerceGraphState(BaseModel):
    conversation_id: UUID

    messages: Annotated[
        list[BaseMessage],
        add_messages,
    ] = Field(default_factory=list)

    session: Annotated[
        CommerceSession | None,
        retain_commerce_session,
    ] = None

    planner_response: Annotated[
        PlannerResponse | None,
        UntrackedValue,
    ] = None

    execution_outcome: Annotated[
        ExecutionOutcome | None,
        UntrackedValue,
    ] = None

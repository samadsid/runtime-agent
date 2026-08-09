from uuid import uuid4

import pytest

from commerce.models import CommerceSession
from runtime.capabilities import ExecutionContext
from runtime.commands import RespondCommand, WaitCommand
from runtime.contracts import GeneratedExecutionOutcome
from runtime.handlers import RespondHandler, WaitHandler


@pytest.mark.asyncio
async def test_planner_respond_outcome_requires_response_composition() -> None:
    result = await RespondHandler[CommerceSession]().handle(
        RespondCommand(message="Approved response."),
        CommerceSession(),
        ExecutionContext(tenant_id=uuid4(), conversation_id=uuid4()),
    )

    assert isinstance(result.outcome, GeneratedExecutionOutcome)


@pytest.mark.asyncio
async def test_wait_outcome_requires_response_composition() -> None:
    result = await WaitHandler[CommerceSession]().handle(
        WaitCommand(reason="pending"),
        CommerceSession(),
        ExecutionContext(tenant_id=uuid4(), conversation_id=uuid4()),
    )

    assert isinstance(result.outcome, GeneratedExecutionOutcome)

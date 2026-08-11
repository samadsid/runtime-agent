from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.models import ChatRequest
from app.api.routes import router
from channels import ChatRequestRecord, ChatRequestStatus


class FakeRuntime:
    def __init__(self) -> None:
        self.calls = []

    async def chat(self, conversation, context):
        self.calls.append((conversation, context))
        conversation.add_assistant_message("Approved reply\nनमस्ते")
        return conversation


class FakeChatRequestRepository:
    def __init__(self) -> None:
        self.records: dict[tuple[UUID, UUID], ChatRequestRecord] = {}
        self.lock_available = True

    async def begin(self, tenant_id, request_id, fingerprint, conversation_id, now):
        del now
        key = (tenant_id, request_id)
        existing = self.records.get(key)
        if existing is not None:
            return existing, False
        record = ChatRequestRecord(
            tenant_id=tenant_id,
            request_id=request_id,
            request_fingerprint=fingerprint,
            conversation_id=conversation_id,
            status=ChatRequestStatus.PENDING,
            reply=None,
        )
        self.records[key] = record
        return record, True

    async def mark_executing(self, tenant_id, request_id, now):
        del now
        key = (tenant_id, request_id)
        current = self.records[key]
        if current.status != ChatRequestStatus.PENDING:
            return False
        self.records[key] = ChatRequestRecord(
            **{**current.__dict__, "status": ChatRequestStatus.EXECUTING}
        )
        return True

    async def complete(self, tenant_id, request_id, reply, now):
        del now
        key = (tenant_id, request_id)
        current = self.records[key]
        self.records[key] = ChatRequestRecord(
            **{
                **current.__dict__,
                "status": ChatRequestStatus.COMPLETED,
                "reply": reply,
            }
        )

    async def mark_ambiguous(self, tenant_id, request_id, now):
        del now
        key = (tenant_id, request_id)
        current = self.records[key]
        self.records[key] = ChatRequestRecord(
            **{**current.__dict__, "status": ChatRequestStatus.AMBIGUOUS}
        )

    @asynccontextmanager
    async def conversation_lock(self, tenant_id, conversation_id):
        del tenant_id, conversation_id
        yield self.lock_available


def _app(allow_identity: bool = True):
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=False,
        allow_methods=["POST", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "X-Dev-Customer-Id",
            "X-Development-Customer-Id",
            "X-Request-Id",
        ],
    )
    app.include_router(router)
    repository = FakeChatRequestRepository()
    runtime = FakeRuntime()
    app.state.application_container = SimpleNamespace(
        settings=SimpleNamespace(
            DEFAULT_TENANT_ID=uuid4(),
            ALLOW_DEVELOPMENT_CUSTOMER_ID_HEADER=allow_identity,
        ),
        chat_request_repository=repository,
        runtime=runtime,
    )
    return app, repository, runtime


@pytest.mark.asyncio
async def test_chat_trims_input_replays_completed_request_and_preserves_context():
    app, _, runtime = _app()
    request_id = uuid4()
    headers = {
        "X-Request-Id": str(request_id),
        "X-Dev-Customer-Id": "browser-id",
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = await client.post(
            "/chat",
            json={"message": "  hello  ", "conversation_id": None},
            headers=headers,
        )
        second = await client.post(
            "/chat", json={"message": "hello", "conversation_id": None}, headers=headers
        )
    assert first.status_code == 200
    assert second.json() == first.json()
    assert len(runtime.calls) == 1
    conversation, context = runtime.calls[0]
    assert conversation.messages[0].content == "hello"
    assert context.channel_customer_id == "browser-id"
    assert context.request_id == f"development-http:{request_id}"


@pytest.mark.asyncio
async def test_chat_rejects_conflicting_identity_and_request_key_reuse():
    app, _, _ = _app()
    request_id = uuid4()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        conflict = await client.post(
            "/chat",
            json={"message": "hello"},
            headers={
                "X-Dev-Customer-Id": "one",
                "X-Development-Customer-Id": "two",
            },
        )
        accepted = await client.post(
            "/chat",
            json={"message": "hello"},
            headers={"X-Request-Id": str(request_id)},
        )
        reused = await client.post(
            "/chat",
            json={"message": "different"},
            headers={"X-Request-Id": str(request_id)},
        )
    assert conflict.status_code == 400
    assert accepted.status_code == 200
    assert reused.status_code == 409


@pytest.mark.asyncio
async def test_chat_validates_body_and_cors_preflight():
    app, _, _ = _app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        blank = await client.post("/chat", json={"message": "   "})
        oversized = await client.post("/chat", json={"message": "x" * 2001})
        preflight = await client.options(
            "/chat",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "X-Request-Id,X-Dev-Customer-Id,Content-Type",
            },
        )
    assert blank.status_code == 422
    assert oversized.status_code == 422
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_chat_request_model_has_bounded_trimmed_message():
    assert ChatRequest(message="  hello  ").message == "hello"

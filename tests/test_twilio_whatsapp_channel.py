from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from urllib.parse import urlencode
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from twilio.request_validator import RequestValidator

from app.api.twilio_whatsapp_webhooks import router
from app.jobs.channel_workers import ChannelInboundProcessor
from channels.models import InboundMessage, InboundStatus, MessageKind
from commerce.models import ChannelName
from infrastructure.channels.twilio import TwilioRequestValidator


class FakeChannelRepository:
    def __init__(self) -> None:
        self.ingested = []
        self.completed = []
        self.failed = []

    async def ingest_inbound(self, **values):
        self.ingested.append(values)
        return object(), True

    async def claim_inbound_batch(self, batch_size, now, lease_seconds):
        return []

    @asynccontextmanager
    async def conversation_lock(self, tenant_id, conversation_id):
        yield True

    async def complete_inbound(self, inbound, reply, sender_id, now):
        self.completed.append((inbound, reply, sender_id))

    async def fail_inbound(self, *args, **kwargs):
        self.failed.append((args, kwargs))


class FakeRuntime:
    def __init__(self) -> None:
        self.calls = []

    async def chat(self, conversation, context):
        self.calls.append((conversation, context))
        conversation.add_assistant_message("Approved reply")
        return conversation


def _app(repository: FakeChannelRepository, token: str = "token") -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    settings = SimpleNamespace(
        TWILIO_WHATSAPP_ENABLED=True,
        TWILIO_ACCOUNT_SID="AC" + "1" * 32,
        TWILIO_WHATSAPP_FROM="whatsapp:+14155238886",
        TWILIO_WHATSAPP_MAX_INBOUND_BODY_BYTES=4096,
        DEFAULT_TENANT_ID=uuid4(),
        twilio_inbound_url="https://channel.example/webhooks/twilio/whatsapp",
        twilio_status_url="https://channel.example/webhooks/twilio/whatsapp/status",
    )
    app.state.application_container = SimpleNamespace(
        settings=settings,
        twilio_request_validator=TwilioRequestValidator(token),
        channel_repository=repository,
    )
    return app


def _fields() -> dict[str, str]:
    return {
        "MessageSid": "SM" + "2" * 32,
        "AccountSid": "AC" + "1" * 32,
        "From": "whatsapp:+919876543210",
        "To": "whatsapp:+14155238886",
        "Body": "नमस्ते",
        "NumMedia": "0",
    }


@pytest.mark.asyncio
async def test_signed_inbound_is_persisted_and_acknowledged_without_runtime() -> None:
    repository = FakeChannelRepository()
    app = _app(repository)
    fields = _fields()
    url = app.state.application_container.settings.twilio_inbound_url
    signature = RequestValidator("token").compute_signature(url, fields)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://internal"
    ) as client:
        response = await client.post(
            "/webhooks/twilio/whatsapp",
            content=urlencode(fields),
            headers={
                "content-type": "application/x-www-form-urlencoded",
                "X-Twilio-Signature": signature,
            },
        )
    assert response.status_code == 200
    assert (
        response.text == '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
    )
    assert repository.ingested[0]["body"] == "नमस्ते"
    assert repository.ingested[0]["message_kind"] == MessageKind.TEXT


@pytest.mark.asyncio
async def test_invalid_signature_has_no_durable_effect() -> None:
    repository = FakeChannelRepository()
    app = _app(repository)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://internal"
    ) as client:
        response = await client.post(
            "/webhooks/twilio/whatsapp",
            content=urlencode(_fields()),
            headers={
                "content-type": "application/x-www-form-urlencoded",
                "X-Twilio-Signature": "invalid",
            },
        )
    assert response.status_code == 403
    assert repository.ingested == []


@pytest.mark.asyncio
async def test_processor_passes_trusted_context_and_persists_reply() -> None:
    now = datetime.now(timezone.utc)
    inbound = InboundMessage(
        id=uuid4(),
        tenant_id=uuid4(),
        channel=ChannelName.TWILIO_WHATSAPP,
        provider_message_id="SM" + "3" * 32,
        conversation_id=uuid4(),
        sender_id="whatsapp:+919876543210",
        recipient_id="whatsapp:+14155238886",
        body="show products",
        message_kind=MessageKind.TEXT,
        status=InboundStatus.PROCESSING,
        attempt_count=1,
        next_attempt_at=now,
        lease_expires_at=now,
        last_error_code=None,
        received_at=now,
        processed_at=None,
    )
    repository = FakeChannelRepository()
    runtime = FakeRuntime()
    processor = ChannelInboundProcessor(
        repository=repository,
        runtime=runtime,
        sender_id="whatsapp:+14155238886",
        batch_size=20,
        lease_seconds=120,
        max_attempts=5,
        interval_seconds=1,
    )
    await processor._process(inbound)
    context = runtime.calls[0][1]
    assert context.conversation_id == inbound.conversation_id
    assert context.channel_customer_id == inbound.sender_id
    assert context.request_id == f"twilio-whatsapp:{inbound.provider_message_id}"
    assert repository.completed[0][1] == "Approved reply"
    assert repository.failed == []


@pytest.mark.asyncio
async def test_unsupported_message_never_invokes_runtime() -> None:
    now = datetime.now(timezone.utc)
    inbound = InboundMessage(
        id=uuid4(),
        tenant_id=uuid4(),
        channel=ChannelName.TWILIO_WHATSAPP,
        provider_message_id="SM" + "4" * 32,
        conversation_id=uuid4(),
        sender_id="whatsapp:+919876543210",
        recipient_id="whatsapp:+14155238886",
        body="",
        message_kind=MessageKind.UNSUPPORTED,
        status=InboundStatus.PROCESSING,
        attempt_count=1,
        next_attempt_at=now,
        lease_expires_at=now,
        last_error_code=None,
        received_at=now,
        processed_at=None,
    )
    repository = FakeChannelRepository()
    runtime = FakeRuntime()
    processor = ChannelInboundProcessor(
        repository, runtime, "whatsapp:+14155238886", 20, 120, 5, 1
    )
    await processor._process(inbound)
    assert runtime.calls == []
    assert "text messages" in repository.completed[0][1]

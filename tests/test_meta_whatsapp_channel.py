from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from app.api.meta_whatsapp_webhooks import router
from app.config.settings import Settings
from app.config.settings import settings as current_settings
from app.jobs.channel_workers import ChannelOutboundDispatcher
from channels.models import (
    ApprovedTemplateMessage,
    MessageKind,
    OutboundMessage,
    OutboundStatus,
    WhatsAppProviderName,
)
from channels.providers import AmbiguousSendError, RetryableSendError
from commerce.models import ChannelName
from infrastructure.channels.meta import (
    MetaSignatureValidator,
    MetaWebhookParser,
    MetaWhatsAppMessageProvider,
)


class FakeMetaRepository:
    def __init__(self) -> None:
        self.calls = []

    async def ingest_meta_batch(self, **values):
        self.calls.append(values)
        return len(values["batch"].inbound), len(values["batch"].statuses)


def _payload(*, include_status: bool = False) -> dict:
    value = {
        "metadata": {"phone_number_id": "456"},
        "messages": [
            {
                "from": "919876543210",
                "id": "wamid." + "A" * 20,
                "timestamp": "1770000000",
                "type": "text",
                "text": {"body": " नमस्ते\nदुकान "},
            }
        ],
    }
    if include_status:
        value["statuses"] = [
            {
                "id": "wamid." + "B" * 20,
                "status": "delivered",
                "timestamp": "1770000001",
            }
        ]
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "123", "changes": [{"field": "messages", "value": value}]}],
    }


def _app(repository: FakeMetaRepository) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.state.application_container = SimpleNamespace(
        settings=SimpleNamespace(
            WHATSAPP_PROVIDER="meta_cloud",
            META_WHATSAPP_VERIFY_TOKEN="verify-secret",
            META_WHATSAPP_MAX_INBOUND_BODY_BYTES=65536,
            DEFAULT_TENANT_ID=uuid4(),
        ),
        meta_signature_validator=MetaSignatureValidator("app-secret"),
        meta_webhook_parser=MetaWebhookParser(
            waba_id="123",
            phone_number_id="456",
            max_text_chars=4096,
            max_text_bytes=65536,
        ),
        channel_repository=repository,
    )
    return app


def _signature(raw: bytes) -> str:
    return "sha256=" + hmac.new(b"app-secret", raw, hashlib.sha256).hexdigest()


def _settings(**updates) -> Settings:
    return Settings.model_validate({**current_settings.model_dump(), **updates})


def test_provider_selection_validates_only_the_selected_provider() -> None:
    _settings(
        WHATSAPP_PROVIDER="disabled",
        TWILIO_ACCOUNT_SID=None,
        META_WHATSAPP_ACCESS_TOKEN=None,
    ).validate_whatsapp_configuration()
    _settings(
        WHATSAPP_PROVIDER="twilio",
        APP_ENV="test",
        TWILIO_ACCOUNT_SID="AC" + "1" * 32,
        TWILIO_AUTH_TOKEN="token",
        TWILIO_WHATSAPP_PUBLIC_BASE_URL="http://test",
        META_WHATSAPP_ACCESS_TOKEN=None,
    ).validate_whatsapp_configuration()
    with pytest.raises(RuntimeError, match="Missing Meta"):
        _settings(
            WHATSAPP_PROVIDER="meta_cloud",
            META_WHATSAPP_PHONE_NUMBER_ID=None,
            META_WHATSAPP_BUSINESS_ACCOUNT_ID=None,
            META_WHATSAPP_ACCESS_TOKEN=None,
            META_WHATSAPP_APP_SECRET=None,
            META_WHATSAPP_VERIFY_TOKEN=None,
            META_WHATSAPP_PUBLIC_BASE_URL=None,
        ).validate_whatsapp_configuration()
    with pytest.raises(ValidationError):
        _settings(WHATSAPP_PROVIDER="unsupported")


def test_valid_meta_configuration_is_bounded_and_explicitly_versioned() -> None:
    configured = _settings(
        WHATSAPP_PROVIDER="meta_cloud",
        APP_ENV="test",
        META_GRAPH_API_VERSION="v25.0",
        META_WHATSAPP_PHONE_NUMBER_ID="123456",
        META_WHATSAPP_BUSINESS_ACCOUNT_ID="987654",
        META_WHATSAPP_ACCESS_TOKEN="access-token",
        META_WHATSAPP_APP_SECRET="a" * 32,
        META_WHATSAPP_VERIFY_TOKEN="b" * 64,
        META_WHATSAPP_PUBLIC_BASE_URL="http://test",
    )
    configured.validate_whatsapp_configuration()
    assert configured.meta_whatsapp_webhook_url == "http://test/webhooks/meta/whatsapp"


@pytest.mark.asyncio
async def test_verification_returns_exact_plain_challenge_without_write() -> None:
    repository = FakeMetaRepository()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app(repository)), base_url="http://test"
    ) as client:
        response = await client.get(
            "/webhooks/meta/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "verify-secret",
                "hub.challenge": "challenge-123",
            },
        )
    assert response.status_code == 200
    assert response.text == "challenge-123"
    assert response.headers["content-type"].startswith("text/plain")
    assert repository.calls == []


@pytest.mark.asyncio
async def test_verification_rejects_missing_token_and_inactive_provider() -> None:
    repository = FakeMetaRepository()
    app = _app(repository)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        missing = await client.get(
            "/webhooks/meta/whatsapp",
            params={"hub.mode": "subscribe", "hub.challenge": "challenge"},
        )
        app.state.application_container.settings.WHATSAPP_PROVIDER = "twilio"
        inactive = await client.get(
            "/webhooks/meta/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "verify-secret",
                "hub.challenge": "challenge",
            },
        )
    assert missing.status_code == 403
    assert inactive.status_code == 404
    assert repository.calls == []


@pytest.mark.asyncio
async def test_signed_batch_is_normalized_and_persisted_once() -> None:
    repository = FakeMetaRepository()
    raw = json.dumps(_payload(include_status=True), ensure_ascii=False).encode()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app(repository)), base_url="http://test"
    ) as client:
        response = await client.post(
            "/webhooks/meta/whatsapp",
            content=raw,
            headers={
                "content-type": "application/json",
                "X-Hub-Signature-256": _signature(raw),
            },
        )
    assert response.status_code == 200
    batch = repository.calls[0]["batch"]
    assert batch.inbound[0].sender_id == "+919876543210"
    assert batch.inbound[0].body == "नमस्ते\nदुकान"
    assert batch.inbound[0].message_kind == MessageKind.TEXT
    assert batch.statuses[0].status == OutboundStatus.DELIVERED


def test_parser_normalizes_exact_location_attachment() -> None:
    payload = _payload()
    payload["entry"][0]["changes"][0]["value"]["messages"] = [
        {
            "from": "919876543210",
            "id": "wamid." + "L" * 20,
            "type": "location",
            "location": {
                "latitude": "28.612345",
                "longitude": "77.234567",
                "name": "  Shared place  ",
                "address": " Provider label ",
            },
        }
    ]
    parser = MetaWebhookParser(
        waba_id="123",
        phone_number_id="456",
        max_text_chars=4096,
        max_text_bytes=65536,
    )
    event = parser.parse(json.dumps(payload).encode()).inbound[0]
    assert event.message_kind is MessageKind.LOCATION
    assert event.location is not None
    assert event.location.latitude == Decimal("28.612345")
    assert event.location.longitude == Decimal("77.234567")
    assert event.location.name == "Shared place"


@pytest.mark.asyncio
async def test_invalid_signature_and_wrong_resource_create_no_rows() -> None:
    repository = FakeMetaRepository()
    raw = json.dumps(_payload()).encode()
    app = _app(repository)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        invalid = await client.post(
            "/webhooks/meta/whatsapp",
            content=raw,
            headers={
                "content-type": "application/json",
                "X-Hub-Signature-256": "sha256=" + "0" * 64,
            },
        )
        wrong = _payload()
        wrong["entry"][0]["id"] = "999"
        wrong_raw = json.dumps(wrong).encode()
        ignored = await client.post(
            "/webhooks/meta/whatsapp",
            content=wrong_raw,
            headers={
                "content-type": "application/json",
                "X-Hub-Signature-256": _signature(wrong_raw),
            },
        )
    assert invalid.status_code == 403
    assert ignored.status_code == 200
    assert repository.calls == []


@pytest.mark.asyncio
async def test_meta_provider_serializes_text_and_template_exactly() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"messages": [{"id": "wamid." + "C" * 20}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = MetaWhatsAppMessageProvider(
            client=client,
            graph_api_version="v25.0",
            phone_number_id="456",
            access_token="secret-token",
            max_text_chars=4096,
        )
        await provider.send_text("+919876543210", "Approved reply", uuid4())
        await provider.send_template(
            "+919876543210",
            ApprovedTemplateMessage(
                key="order.confirmed.en-IN",
                name="order_confirmed_v1",
                language="en_US",
                parameters={"1": "ORDER-1", "2": "COD"},
            ),
            uuid4(),
        )
    text = json.loads(requests[0].content)
    template = json.loads(requests[1].content)
    assert requests[0].url.path == "/v25.0/456/messages"
    assert requests[0].headers["authorization"] == "Bearer secret-token"
    assert text["to"] == "919876543210"
    assert text["text"] == {"preview_url": False, "body": "Approved reply"}
    assert template["template"]["language"] == {"code": "en_US"}
    assert template["template"]["components"][0]["parameters"][0]["text"] == "ORDER-1"


@pytest.mark.asyncio
async def test_meta_provider_classifies_retryable_and_ambiguous_results() -> None:
    async def retry_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(retry_handler)
    ) as client:
        provider = MetaWhatsAppMessageProvider(
            client=client,
            graph_api_version="v25.0",
            phone_number_id="456",
            access_token="token",
            max_text_chars=4096,
        )
        with pytest.raises(RetryableSendError):
            await provider.send_text("+919876543210", "hello", uuid4())

    async def ambiguous_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"messages": []})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(ambiguous_handler)
    ) as client:
        provider = MetaWhatsAppMessageProvider(
            client=client,
            graph_api_version="v25.0",
            phone_number_id="456",
            access_token="token",
            max_text_chars=4096,
        )
        with pytest.raises(AmbiguousSendError):
            await provider.send_text("+919876543210", "hello", uuid4())


@pytest.mark.asyncio
async def test_dispatcher_marks_possible_acceptance_ambiguous_without_retry() -> None:
    now = datetime.now(timezone.utc)

    class Repository:
        def __init__(self) -> None:
            self.started = []
            self.failed = []

        async def conversation_last_inbound(self, conversation_id):
            return now

        async def mark_send_started(self, outbound_id, started_at):
            self.started.append(outbound_id)

        async def fail_outbound(self, *args):
            self.failed.append(args)

    class Provider:
        async def send_text(self, recipient_id, body, idempotency_key):
            raise AmbiguousSendError("possible_acceptance")

    repository = Repository()
    outbound = OutboundMessage(
        id=uuid4(),
        tenant_id=uuid4(),
        channel=ChannelName.WHATSAPP,
        provider=WhatsAppProviderName.META_CLOUD,
        conversation_id=uuid4(),
        source_inbound_id=uuid4(),
        recipient_id="+919876543210",
        sender_id="456",
        body="Approved reply",
        status=OutboundStatus.SENDING,
        attempt_count=1,
        next_attempt_at=now,
        lease_expires_at=now,
        provider_message_id=None,
        last_error_code=None,
        created_at=now,
        sent_at=None,
        updated_at=now,
    )
    dispatcher = ChannelOutboundDispatcher(
        repository=repository,
        provider=Provider(),
        batch_size=20,
        lease_seconds=120,
        max_attempts=5,
        interval_seconds=1,
        window_hours=24,
        provider_name=WhatsAppProviderName.META_CLOUD,
    )
    await dispatcher._dispatch(outbound)
    assert repository.started == [outbound.id]
    assert repository.failed[0][1] == OutboundStatus.AMBIGUOUS
    assert repository.failed[0][2] == "possible_acceptance"

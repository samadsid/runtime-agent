import json
from datetime import datetime, timezone
from hashlib import sha256
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException, Request, Response

from app.api.models import (
    ChatRequest,
    ChatResponse,
)
from channels import ChatRequestStatus
from commerce.models import ChannelName, ProviderPaymentStatus
from commerce.payments import PaymentProviderInvalidResponseError
from runtime.contracts import (
    ConversationState,
    CustomerChannelContext,
)

router = APIRouter()


@router.post("/payments/webhooks/fake", status_code=204)
async def fake_payment_webhook(
    request: Request,
    signature: str | None = Header(default=None, alias="X-Payment-Signature"),
) -> Response:
    container = request.app.state.application_container
    client = request.client.host if request.client else "unknown"
    if not await container.payment_rate_limiter.allow(
        f"webhook:{client}", container.settings.PAYMENT_WEBHOOK_RATE_LIMIT_PER_MINUTE
    ):
        raise HTTPException(status_code=429, detail="Too many payment requests.")
    if signature is None:
        raise HTTPException(status_code=400, detail="Missing payment signature.")
    raw_body = await request.body()
    try:
        await request.app.state.application_container.payment_event_service.ingest(
            raw_body, signature
        )
    except PaymentProviderInvalidResponseError as exc:
        raise HTTPException(status_code=400, detail="Invalid payment webhook.") from exc
    return Response(status_code=204)


async def _simulate_payment(
    request: Request, provider_payment_id: str, status: ProviderPaymentStatus
) -> Response:
    container = request.app.state.application_container
    if container.settings.APP_ENV not in {"development", "test"}:
        raise HTTPException(status_code=404, detail="Not found.")
    client = request.client.host if request.client else "unknown"
    if not await container.payment_rate_limiter.allow(
        f"simulate:{client}:{provider_payment_id}",
        container.settings.FAKE_PAYMENT_RATE_LIMIT_PER_MINUTE,
    ):
        raise HTTPException(status_code=429, detail="Too many payment requests.")
    try:
        raw, signature = await container.payment_provider.simulate(
            provider_payment_id, status
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Fake payment not found.") from exc
    await container.payment_event_service.ingest(raw, signature)
    return Response(status_code=204)


@router.post("/dev/payments/{provider_payment_id}/succeed", status_code=204)
async def succeed_fake_payment(provider_payment_id: str, request: Request) -> Response:
    return await _simulate_payment(
        request, provider_payment_id, ProviderPaymentStatus.SUCCEEDED
    )


@router.post("/dev/payments/{provider_payment_id}/fail", status_code=204)
async def fail_fake_payment(provider_payment_id: str, request: Request) -> Response:
    return await _simulate_payment(
        request, provider_payment_id, ProviderPaymentStatus.FAILED
    )


@router.post("/dev/payments/{provider_payment_id}/expire", status_code=204)
async def expire_fake_payment(provider_payment_id: str, request: Request) -> Response:
    return await _simulate_payment(
        request, provider_payment_id, ProviderPaymentStatus.EXPIRED
    )


@router.post(
    "/chat",
    response_model=ChatResponse,
)
async def chat(
    body: ChatRequest,
    request: Request,
    development_customer_id: str | None = Header(
        default=None, alias="X-Dev-Customer-Id"
    ),
    legacy_development_customer_id: str | None = Header(
        default=None, alias="X-Development-Customer-Id"
    ),
    request_id: Annotated[UUID | None, Header(alias="X-Request-Id")] = None,
) -> ChatResponse:
    application_container = request.app.state.application_container
    canonical_customer_id = _normalize_customer_id(development_customer_id)
    legacy_customer_id = _normalize_customer_id(legacy_development_customer_id)
    if (
        canonical_customer_id is not None
        and legacy_customer_id is not None
        and canonical_customer_id != legacy_customer_id
    ):
        raise HTTPException(status_code=400, detail="Conflicting customer identity.")
    normalized_customer_id = canonical_customer_id or legacy_customer_id
    if normalized_customer_id is not None and not (
        application_container.settings.ALLOW_DEVELOPMENT_CUSTOMER_ID_HEADER
    ):
        raise HTTPException(
            status_code=400,
            detail="Development customer identity is disabled.",
        )

    logical_request_id = request_id or uuid4()
    request_fingerprint = _chat_request_fingerprint(
        body.message, body.conversation_id, normalized_customer_id
    )
    tenant_id = application_container.settings.DEFAULT_TENANT_ID
    record, request_created = await application_container.chat_request_repository.begin(
        tenant_id,
        logical_request_id,
        request_fingerprint,
        body.conversation_id or uuid4(),
        datetime.now(timezone.utc),
    )
    if record.request_fingerprint != request_fingerprint:
        raise HTTPException(status_code=409, detail="Request identifier conflict.")
    if record.status == ChatRequestStatus.COMPLETED:
        return ChatResponse(
            conversation_id=record.conversation_id,
            reply=record.reply or "",
        )
    if record.status in {ChatRequestStatus.EXECUTING, ChatRequestStatus.AMBIGUOUS}:
        raise HTTPException(status_code=409, detail="Request outcome is pending.")

    async with application_container.chat_request_repository.conversation_lock(
        tenant_id, record.conversation_id
    ) as acquired:
        if not acquired:
            raise HTTPException(status_code=409, detail="Conversation is busy.")
        executing = await application_container.chat_request_repository.mark_executing(
            tenant_id, logical_request_id, datetime.now(timezone.utc)
        )
        if not executing:
            raise HTTPException(status_code=409, detail="Request is already active.")
        try:
            conversation = ConversationState(conversation_id=record.conversation_id)
            conversation.add_user_message(body.message)
            customer_context = CustomerChannelContext(
                tenant_id=tenant_id,
                conversation_id=record.conversation_id,
                channel=ChannelName.DEVELOPMENT_HTTP,
                channel_customer_id=normalized_customer_id,
                request_id=f"development-http:{logical_request_id}",
                conversation_entry=request_created and body.conversation_id is None,
            )
            conversation = await application_container.runtime.chat(
                conversation, customer_context
            )
            reply = (
                conversation.latest_message.content
                if conversation.latest_message
                else ""
            )
            await application_container.chat_request_repository.complete(
                tenant_id,
                logical_request_id,
                reply,
                datetime.now(timezone.utc),
            )
        except Exception:
            await application_container.chat_request_repository.mark_ambiguous(
                tenant_id, logical_request_id, datetime.now(timezone.utc)
            )
            raise

    return ChatResponse(conversation_id=record.conversation_id, reply=reply)


def _normalize_customer_id(value: str | None) -> str | None:
    normalized = value.strip() if value is not None else None
    return normalized or None


def _chat_request_fingerprint(
    message: str, conversation_id: UUID | None, customer_id: str | None
) -> str:
    payload = json.dumps(
        {
            "message": message,
            "conversation_id": str(conversation_id) if conversation_id else None,
            "customer_id": customer_id,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256(payload.encode("utf-8")).hexdigest()

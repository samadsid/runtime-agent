from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Request, Response

from app.api.models import (
    ChatRequest,
    ChatResponse,
)
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
        default=None, alias="X-Development-Customer-Id"
    ),
) -> ChatResponse:

    conversation_id = (
        body.conversation_id if body.conversation_id is not None else uuid4()
    )

    conversation = ConversationState(
        conversation_id=conversation_id,
    )

    conversation.add_user_message(
        body.message,
    )

    application_container = request.app.state.application_container
    if (
        development_customer_id is not None
        and not application_container.settings.ALLOW_DEVELOPMENT_CUSTOMER_ID_HEADER
    ):
        raise HTTPException(
            status_code=400,
            detail="Development customer identity is disabled.",
        )
    normalized_customer_id = (
        development_customer_id.strip() if development_customer_id is not None else None
    )
    if normalized_customer_id == "":
        normalized_customer_id = None
    customer_context = CustomerChannelContext(
        tenant_id=application_container.settings.DEFAULT_TENANT_ID,
        conversation_id=conversation_id,
        channel=ChannelName.DEVELOPMENT_HTTP,
        channel_customer_id=normalized_customer_id,
    )

    conversation = await application_container.runtime.chat(
        conversation, customer_context
    )

    return ChatResponse(
        conversation_id=conversation.conversation_id,
        reply=conversation.latest_message.content
        if conversation.latest_message
        else "",
    )

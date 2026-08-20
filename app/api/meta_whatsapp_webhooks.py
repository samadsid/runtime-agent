from __future__ import annotations

import hmac
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.observability import DELIVERY_EVENTS, WEBHOOKS, WHATSAPP_INBOUND_MESSAGES
from infrastructure.channels.meta import MetaOwnershipMismatch, MetaWebhookParseError

router = APIRouter()


def _active(request: Request):
    container = request.app.state.application_container
    if container.settings.WHATSAPP_PROVIDER != "meta_cloud":
        raise HTTPException(status_code=404, detail="Not found.")
    return container


@router.get("/webhooks/meta/whatsapp")
async def verify_meta_whatsapp(
    request: Request,
    mode: str | None = Query(default=None, alias="hub.mode"),
    token: str | None = Query(default=None, alias="hub.verify_token"),
    challenge: str | None = Query(default=None, alias="hub.challenge"),
) -> Response:
    container = _active(request)
    configured = container.settings.META_WHATSAPP_VERIFY_TOKEN or ""
    if (
        mode != "subscribe"
        or token is None
        or challenge is None
        or not token
        or not challenge
        or len(token) > 512
        or len(challenge) > 512
        or not hmac.compare_digest(token, configured)
    ):
        raise HTTPException(status_code=403, detail="Verification rejected.")
    return Response(challenge, media_type="text/plain")


@router.post("/webhooks/meta/whatsapp")
async def meta_whatsapp_events(request: Request) -> Response:
    container = _active(request)
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip()
    if content_type != "application/json":
        raise HTTPException(status_code=415, detail="Unsupported content type.")
    limit = container.settings.META_WHATSAPP_MAX_INBOUND_BODY_BYTES
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > limit:
                raise HTTPException(status_code=413, detail="Webhook is too large.")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Malformed webhook.") from exc
    raw = await request.body()
    if len(raw) > limit:
        raise HTTPException(status_code=413, detail="Webhook is too large.")
    signatures = request.headers.getlist("x-hub-signature-256")
    signature = signatures[0] if len(signatures) == 1 else None
    if not container.meta_signature_validator.validate(raw, signature):
        WEBHOOKS.labels("whatsapp", "signature", "invalid").inc()
        raise HTTPException(status_code=403, detail="Invalid webhook signature.")
    try:
        batch = container.meta_webhook_parser.parse(raw)
    except MetaOwnershipMismatch:
        WEBHOOKS.labels("whatsapp", "ownership", "ignored").inc()
        return Response(status_code=200)
    except MetaWebhookParseError as exc:
        WEBHOOKS.labels("whatsapp", "envelope", "rejected").inc()
        raise HTTPException(status_code=400, detail="Malformed webhook.") from exc
    inbound, _ = await container.channel_repository.ingest_meta_batch(
        tenant_id=container.settings.DEFAULT_TENANT_ID,
        batch=batch,
        received_at=datetime.now(timezone.utc),
    )
    WEBHOOKS.labels("whatsapp", "inbound", "accepted" if inbound else "duplicate").inc()
    for message in batch.inbound:
        WHATSAPP_INBOUND_MESSAGES.labels(
            message.message_kind.value.lower(), "accepted" if inbound else "duplicate"
        ).inc()
    for event in batch.statuses:
        DELIVERY_EVENTS.labels("whatsapp", event.status.value.lower()).inc()
    return Response(status_code=200)

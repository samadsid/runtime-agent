from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import parse_qsl

from fastapi import APIRouter, HTTPException, Request, Response

from app.observability import OUTBOUND, WEBHOOKS
from channels.models import MessageKind, OutboundStatus

router = APIRouter()
_MESSAGE_SID = re.compile(r"^SM[0-9A-Fa-f]{32}$")
_ACCOUNT_SID = re.compile(r"^AC[0-9A-Fa-f]{32}$")
_WHATSAPP_E164 = re.compile(r"^whatsapp:\+[1-9][0-9]{7,14}$")
_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


async def _signed_form(request: Request, url: str) -> dict[str, str]:
    container = request.app.state.application_container
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip()
    if content_type != "application/x-www-form-urlencoded":
        raise HTTPException(status_code=415, detail="Unsupported content type.")
    content_length = request.headers.get("content-length")
    request_limit = container.settings.TWILIO_WHATSAPP_MAX_INBOUND_BODY_BYTES + 16384
    if content_length:
        try:
            if int(content_length) > request_limit:
                raise HTTPException(status_code=413, detail="Webhook is too large.")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Malformed webhook.") from exc
    raw = await request.body()
    if len(raw) > request_limit:
        raise HTTPException(status_code=413, detail="Webhook is too large.")
    try:
        parameters = dict(parse_qsl(raw.decode("utf-8"), keep_blank_values=True))
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="Malformed webhook.") from exc
    signature = request.headers.get("X-Twilio-Signature")
    if not container.twilio_request_validator.validate(url, parameters, signature):
        WEBHOOKS.labels("twilio_whatsapp", "signature", "invalid").inc()
        raise HTTPException(status_code=403, detail="Invalid webhook signature.")
    return parameters


@router.post("/webhooks/twilio/whatsapp")
async def twilio_whatsapp_inbound(request: Request) -> Response:
    container = request.app.state.application_container
    if not container.settings.TWILIO_WHATSAPP_ENABLED:
        raise HTTPException(status_code=404, detail="Not found.")
    fields = await _signed_form(request, container.settings.twilio_inbound_url)
    sid = fields.get("MessageSid", "")
    account_sid = fields.get("AccountSid", "")
    sender = fields.get("From", "")
    recipient = fields.get("To", "")
    body = fields.get("Body", "")
    try:
        media_count = int(fields.get("NumMedia", "0"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Malformed webhook.") from exc
    if (
        not _MESSAGE_SID.fullmatch(sid)
        or not _ACCOUNT_SID.fullmatch(account_sid)
        or account_sid != container.settings.TWILIO_ACCOUNT_SID
        or not _WHATSAPP_E164.fullmatch(sender)
        or not _WHATSAPP_E164.fullmatch(recipient)
        or recipient != container.settings.TWILIO_WHATSAPP_FROM
        or media_count < 0
    ):
        WEBHOOKS.labels("twilio_whatsapp", "inbound", "rejected").inc()
        raise HTTPException(status_code=400, detail="Malformed webhook.")
    if (
        len(body.encode("utf-8"))
        > container.settings.TWILIO_WHATSAPP_MAX_INBOUND_BODY_BYTES
    ):
        raise HTTPException(status_code=413, detail="Message is too large.")
    normalized = body.strip()
    kind = MessageKind.TEXT if normalized else MessageKind.UNSUPPORTED
    inbound, created = await container.channel_repository.ingest_inbound(
        tenant_id=container.settings.DEFAULT_TENANT_ID,
        provider_message_id=sid,
        sender_id=sender,
        recipient_id=recipient,
        body=normalized,
        message_kind=kind,
        received_at=datetime.now(timezone.utc),
    )
    del inbound
    WEBHOOKS.labels(
        "twilio_whatsapp", "inbound", "accepted" if created else "duplicate"
    ).inc()
    return Response(content=_TWIML, media_type="application/xml")


@router.post("/webhooks/twilio/whatsapp/status", status_code=204)
async def twilio_whatsapp_status(request: Request) -> Response:
    container = request.app.state.application_container
    if not container.settings.TWILIO_WHATSAPP_ENABLED:
        raise HTTPException(status_code=404, detail="Not found.")
    fields = await _signed_form(request, container.settings.twilio_status_url)
    sid = fields.get("MessageSid", "")
    account_sid = fields.get("AccountSid", "")
    mapping = {
        "queued": OutboundStatus.ACCEPTED,
        "sent": OutboundStatus.SENT,
        "delivered": OutboundStatus.DELIVERED,
        "read": OutboundStatus.READ,
        "failed": OutboundStatus.FAILED,
        "undelivered": OutboundStatus.FAILED,
    }
    status = mapping.get(fields.get("MessageStatus", "").lower())
    if (
        not _MESSAGE_SID.fullmatch(sid)
        or account_sid != container.settings.TWILIO_ACCOUNT_SID
        or status is None
    ):
        raise HTTPException(status_code=400, detail="Malformed status callback.")
    error_code = fields.get("ErrorCode")
    await container.channel_repository.record_delivery_event(
        sid, status, error_code, datetime.now(timezone.utc)
    )
    OUTBOUND.labels("twilio_whatsapp", status.value.lower()).inc()
    return Response(status_code=204)

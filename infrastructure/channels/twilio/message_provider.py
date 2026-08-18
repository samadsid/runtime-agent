from __future__ import annotations

import asyncio
import json
from uuid import UUID

from channels.models import (
    ApprovedTemplateMessage,
    OutboundStatus,
    ProviderMessageResult,
)
from channels.providers import (
    AmbiguousSendError,
    PermanentSendError,
    RetryableSendError,
)

TwilioRetryableSendError = RetryableSendError
TwilioPermanentSendError = PermanentSendError
TwilioAmbiguousSendError = AmbiguousSendError


class TwilioWhatsAppMessageProvider:
    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        sender_id: str,
        max_body_chars: int,
        status_callback_url: str,
    ) -> None:
        from twilio.rest import Client

        self._client = Client(account_sid, auth_token)
        self._sender_id = sender_id
        self._max_body_chars = max_body_chars
        self._status_callback_url = status_callback_url

    async def send_text(
        self,
        recipient_id: str,
        body: str,
        idempotency_key: UUID,
    ) -> ProviderMessageResult:
        del idempotency_key  # Twilio message creation has no universal idempotency key.
        recipient = self._twilio_recipient(recipient_id)
        if not body or len(body) > self._max_body_chars:
            raise TwilioPermanentSendError("invalid_body_length")
        try:
            message = await asyncio.to_thread(
                self._client.messages.create,
                from_=self._sender_id,
                to=recipient,
                body=body,
                status_callback=self._status_callback_url,
            )
        except Exception as exc:
            # Imports stay local to the provider boundary.
            from requests import Timeout
            from twilio.base.exceptions import TwilioRestException

            if isinstance(exc, Timeout):
                raise TwilioAmbiguousSendError("ambiguous_timeout") from exc
            if isinstance(exc, TwilioRestException):
                if exc.status >= 500 or exc.status == 429:
                    raise TwilioRetryableSendError(f"twilio_http_{exc.status}") from exc
                raise TwilioPermanentSendError(f"twilio_http_{exc.status}") from exc
            raise TwilioRetryableSendError("provider_unavailable") from exc
        if not message.sid:
            raise TwilioAmbiguousSendError("missing_provider_sid")
        return ProviderMessageResult(
            provider_message_id=message.sid, status=OutboundStatus.ACCEPTED
        )

    async def send_template(
        self,
        recipient_id: str,
        template: ApprovedTemplateMessage,
        idempotency_key: UUID,
    ) -> ProviderMessageResult:
        del idempotency_key
        recipient = self._twilio_recipient(recipient_id)
        if not template.name.startswith("HX") or not template.parameters:
            raise TwilioPermanentSendError("invalid_content_template")
        try:
            message = await asyncio.to_thread(
                self._client.messages.create,
                from_=self._sender_id,
                to=recipient,
                content_sid=template.name,
                content_variables=json.dumps(template.parameters, ensure_ascii=False),
                status_callback=self._status_callback_url,
            )
        except Exception as exc:
            from requests import Timeout
            from twilio.base.exceptions import TwilioRestException

            if isinstance(exc, Timeout):
                raise TwilioAmbiguousSendError("ambiguous_timeout") from exc
            if isinstance(exc, TwilioRestException):
                if exc.status >= 500 or exc.status == 429:
                    raise TwilioRetryableSendError(f"twilio_http_{exc.status}") from exc
                raise TwilioPermanentSendError(f"twilio_http_{exc.status}") from exc
            raise TwilioRetryableSendError("provider_unavailable") from exc
        if not message.sid:
            raise TwilioAmbiguousSendError("missing_provider_sid")
        return ProviderMessageResult(provider_message_id=message.sid)

    @staticmethod
    def _twilio_recipient(recipient_id: str) -> str:
        value = recipient_id.removeprefix("whatsapp:")
        if not value.startswith("+") or not value[1:].isdigit():
            raise TwilioPermanentSendError("invalid_recipient")
        return f"whatsapp:{value}"

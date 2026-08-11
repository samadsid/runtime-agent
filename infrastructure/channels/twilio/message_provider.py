from __future__ import annotations

import asyncio
from uuid import UUID

from channels.models import OutboundStatus, ProviderMessageResult


class TwilioRetryableSendError(RuntimeError):
    pass


class TwilioPermanentSendError(RuntimeError):
    pass


class TwilioAmbiguousSendError(RuntimeError):
    pass


class TwilioWhatsAppMessageProvider:
    def __init__(
        self, account_sid: str, auth_token: str, sender_id: str, max_body_chars: int
    ) -> None:
        from twilio.rest import Client

        self._client = Client(account_sid, auth_token)
        self._sender_id = sender_id
        self._max_body_chars = max_body_chars

    async def send_text(
        self,
        recipient_id: str,
        body: str,
        idempotency_key: UUID,
        status_callback_url: str,
    ) -> ProviderMessageResult:
        del idempotency_key  # Twilio message creation has no universal idempotency key.
        if not body or len(body) > self._max_body_chars:
            raise TwilioPermanentSendError("invalid_body_length")
        try:
            message = await asyncio.to_thread(
                self._client.messages.create,
                from_=self._sender_id,
                to=recipient_id,
                body=body,
                status_callback=status_callback_url,
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

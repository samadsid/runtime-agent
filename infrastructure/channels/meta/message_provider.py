from __future__ import annotations

import re
from uuid import UUID

import httpx

from channels.models import ApprovedTemplateMessage, ProviderMessageResult
from channels.providers import (
    AmbiguousSendError,
    PermanentSendError,
    RetryableSendError,
)

_RECIPIENT = re.compile(r"^\+[1-9][0-9]{7,14}$")
_WAMID = re.compile(r"^wamid\.[A-Za-z0-9_:\-./+=]{1,248}$")
_TEMPORARY_META_CODES = {1, 2, 4, 17, 32, 613, 130429, 131000, 131016}


class MetaWhatsAppMessageProvider:
    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        graph_api_version: str,
        phone_number_id: str,
        access_token: str,
        max_text_chars: int,
    ) -> None:
        self._client = client
        self._url = (
            f"https://graph.facebook.com/{graph_api_version}/{phone_number_id}/messages"
        )
        self._headers = {"Authorization": f"Bearer {access_token}"}
        self._max_text_chars = max_text_chars

    async def send_text(
        self, recipient_id: str, body: str, idempotency_key: UUID
    ) -> ProviderMessageResult:
        del idempotency_key
        if _RECIPIENT.fullmatch(recipient_id) is None:
            raise PermanentSendError("invalid_recipient")
        if not body or len(body) > self._max_text_chars:
            raise PermanentSendError("body_too_long")
        return await self._post(
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": recipient_id[1:],
                "type": "text",
                "text": {"preview_url": False, "body": body},
            }
        )

    async def send_template(
        self,
        recipient_id: str,
        template: ApprovedTemplateMessage,
        idempotency_key: UUID,
    ) -> ProviderMessageResult:
        del idempotency_key
        if _RECIPIENT.fullmatch(recipient_id) is None:
            raise PermanentSendError("invalid_recipient")
        if not template.name or not template.language:
            raise PermanentSendError("invalid_template")
        try:
            ordered = [
                value
                for _, value in sorted(
                    template.parameters.items(), key=lambda item: int(item[0])
                )
            ]
        except ValueError as exc:
            raise PermanentSendError("invalid_template_parameters") from exc
        components = []
        if ordered:
            components.append(
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": value} for value in ordered
                    ],
                }
            )
        return await self._post(
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": recipient_id[1:],
                "type": "template",
                "template": {
                    "name": template.name,
                    "language": {"code": template.language},
                    "components": components,
                },
            }
        )

    async def _post(self, payload: dict[str, object]) -> ProviderMessageResult:
        try:
            response = await self._client.post(
                self._url, headers=self._headers, json=payload
            )
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
            raise RetryableSendError("meta_connect_failure") from exc
        except (
            httpx.ReadTimeout,
            httpx.WriteTimeout,
            httpx.WriteError,
            httpx.ReadError,
            httpx.TransportError,
        ) as exc:
            raise AmbiguousSendError("meta_ambiguous_transport") from exc
        error_code = self._error_code(response)
        if (
            response.status_code == 429
            or response.status_code >= 500
            or error_code in _TEMPORARY_META_CODES
        ):
            raise RetryableSendError(f"meta_http_{response.status_code}")
        if response.status_code >= 400:
            raise PermanentSendError(f"meta_http_{response.status_code}")
        try:
            data = response.json()
            wamid = data["messages"][0]["id"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise AmbiguousSendError("missing_provider_wamid") from exc
        if not isinstance(wamid, str) or _WAMID.fullmatch(wamid) is None:
            raise AmbiguousSendError("invalid_provider_wamid")
        return ProviderMessageResult(provider_message_id=wamid)

    @staticmethod
    def _error_code(response: httpx.Response) -> int | None:
        try:
            code = response.json().get("error", {}).get("code")
        except (ValueError, AttributeError):
            return None
        return code if isinstance(code, int) else None

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from channels.models import (
    MessageKind,
    NormalizedDeliveryStatusEvent,
    NormalizedInboundEvent,
    NormalizedWebhookBatch,
    OutboundStatus,
)
from commerce.models import InboundLocation

_WAMID = re.compile(r"^wamid\.[A-Za-z0-9_:\-./+=]{1,248}$")
_DIGITS = re.compile(r"^[1-9][0-9]{7,14}$")
_MAX_ITEMS = 100


class MetaWebhookParseError(ValueError):
    pass


class MetaOwnershipMismatch(ValueError):
    pass


NormalizedMetaInbound = NormalizedInboundEvent
NormalizedMetaStatus = NormalizedDeliveryStatusEvent
MetaWebhookBatch = NormalizedWebhookBatch


class MetaWebhookParser:
    def __init__(
        self,
        *,
        waba_id: str,
        phone_number_id: str,
        max_text_chars: int,
        max_text_bytes: int,
        decimal_places: int = 6,
    ) -> None:
        self._waba_id = waba_id
        self._phone_number_id = phone_number_id
        self._max_text_chars = max_text_chars
        self._max_text_bytes = max_text_bytes
        self._coordinate_quantum = Decimal(1).scaleb(-decimal_places)

    def parse(self, raw: bytes) -> MetaWebhookBatch:
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MetaWebhookParseError("malformed_json") from exc
        if not isinstance(payload, dict):
            raise MetaWebhookParseError("invalid_envelope")
        if payload.get("object") != "whatsapp_business_account":
            raise MetaOwnershipMismatch("wrong_webhook_family")
        entries = payload.get("entry", [])
        if not isinstance(entries, list) or len(entries) > _MAX_ITEMS:
            raise MetaWebhookParseError("invalid_entries")
        inbound: list[NormalizedMetaInbound] = []
        statuses: list[NormalizedMetaStatus] = []
        skipped = 0
        for entry in entries:
            if not isinstance(entry, dict):
                skipped += 1
                continue
            if str(entry.get("id", "")) != self._waba_id:
                raise MetaOwnershipMismatch("wrong_waba")
            changes = entry.get("changes", [])
            if not isinstance(changes, list) or len(changes) > _MAX_ITEMS:
                skipped += 1
                continue
            for change in changes:
                if not isinstance(change, dict) or change.get("field") != "messages":
                    skipped += 1
                    continue
                value = change.get("value")
                if not isinstance(value, dict):
                    skipped += 1
                    continue
                metadata = value.get("metadata", {})
                if not isinstance(metadata, dict):
                    skipped += 1
                    continue
                resource = str(metadata.get("phone_number_id", ""))
                if resource != self._phone_number_id:
                    raise MetaOwnershipMismatch("wrong_phone_number_id")
                recipient = resource
                for message in self._bounded_list(value.get("messages")):
                    normalized = self._message(message, recipient)
                    if normalized is None:
                        skipped += 1
                    else:
                        inbound.append(normalized)
                for status in self._bounded_list(value.get("statuses")):
                    normalized_status = self._status(status)
                    if normalized_status is None:
                        skipped += 1
                    else:
                        statuses.append(normalized_status)
        return MetaWebhookBatch(tuple(inbound), tuple(statuses), skipped)

    @staticmethod
    def _bounded_list(value: Any) -> list[Any]:
        return value if isinstance(value, list) and len(value) <= _MAX_ITEMS else []

    def _message(self, value: Any, recipient: str) -> NormalizedMetaInbound | None:
        if not isinstance(value, dict):
            return None
        wamid = str(value.get("id", ""))
        sender = str(value.get("from", ""))
        if _WAMID.fullmatch(wamid) is None or _DIGITS.fullmatch(sender) is None:
            return None
        kind = MessageKind.UNSUPPORTED
        body = ""
        location = None
        if value.get("type") == "text" and isinstance(value.get("text"), dict):
            candidate = value["text"].get("body")
            if isinstance(candidate, str):
                body = candidate.strip()
                if (
                    body
                    and len(body) <= self._max_text_chars
                    and len(body.encode("utf-8")) <= self._max_text_bytes
                ):
                    kind = MessageKind.TEXT
                else:
                    body = ""
        elif value.get("type") == "location" and isinstance(
            value.get("location"), dict
        ):
            raw_location = value["location"]
            body = "[invalid-location]"
            try:
                if "live_period" in raw_location:
                    raise ValueError("live_location_unsupported")
                location = InboundLocation(
                    latitude=self._decimal_coordinate(raw_location.get("latitude")),
                    longitude=self._decimal_coordinate(raw_location.get("longitude")),
                    name=self._bounded_optional_text(raw_location.get("name"), 200),
                    provider_address=self._bounded_optional_text(
                        raw_location.get("address"), 500
                    ),
                )
                kind = MessageKind.LOCATION
                body = ""
            except (InvalidOperation, ValueError):
                location = None
        return NormalizedMetaInbound(
            wamid, f"+{sender}", recipient, body, kind, location
        )

    def _decimal_coordinate(self, value: Any) -> Decimal:
        if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
            raise ValueError("invalid_coordinate")  # noqa: TRY004
        coordinate = Decimal(str(value))
        if not coordinate.is_finite():
            raise ValueError("invalid_coordinate")
        return coordinate.quantize(self._coordinate_quantum)

    @staticmethod
    def _bounded_optional_text(value: Any, maximum: int) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("invalid_location_text")  # noqa: TRY004
        normalized = " ".join(value.split())
        if len(normalized) > maximum:
            raise ValueError("invalid_location_text")
        return normalized or None

    @staticmethod
    def _status(value: Any) -> NormalizedMetaStatus | None:
        if not isinstance(value, dict):
            return None
        wamid = str(value.get("id", ""))
        mapping = {
            "sent": OutboundStatus.SENT,
            "delivered": OutboundStatus.DELIVERED,
            "read": OutboundStatus.READ,
            "failed": OutboundStatus.FAILED,
        }
        status = mapping.get(str(value.get("status", "")).lower())
        if _WAMID.fullmatch(wamid) is None or status is None:
            return None
        event_at = None
        timestamp = value.get("timestamp")
        if isinstance(timestamp, str) and timestamp.isdigit():
            try:
                event_at = datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
            except (OverflowError, OSError, ValueError):
                event_at = None
        error_code = None
        errors = value.get("errors")
        if isinstance(errors, list) and errors and isinstance(errors[0], dict):
            raw_code = errors[0].get("code")
            if isinstance(raw_code, (str, int)):
                error_code = str(raw_code)[:64]
        return NormalizedMetaStatus(wamid, status, event_at, error_code)

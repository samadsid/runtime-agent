from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone

import asyncpg
from pydantic import ValidationError

from app.jobs.channel_workers import PeriodicChannelWorker
from app.observability import (
    NOTIFICATION_EVENTS,
    NOTIFICATION_LATENCY,
    NOTIFICATION_LOCALE_FALLBACK,
    NOTIFICATION_WORKER_HEALTH,
)
from commerce.models import (
    ChannelName,
    NotificationContentMode,
    NotificationEvent,
    NotificationStatus,
)
from commerce.services import NotificationTemplateError, NotificationTemplateRegistry
from infrastructure.database.repositories import (
    PostgresChannelRepository,
    PostgresNotificationOutboxRepository,
)

logger = logging.getLogger(__name__)


class NotificationOutboxProcessor(PeriodicChannelWorker):
    def __init__(
        self,
        repository: PostgresNotificationOutboxRepository,
        channel_repository: PostgresChannelRepository,
        templates: NotificationTemplateRegistry,
        sender_id: str,
        batch_size: int,
        lease_seconds: int,
        max_attempts: int,
        max_retry_delay_seconds: int,
        interval_seconds: float,
        window_hours: int,
        whatsapp_enabled: bool,
    ) -> None:
        super().__init__(interval_seconds, "notifications")
        self._repository = repository
        self._channel_repository = channel_repository
        self._templates = templates
        self._sender_id = sender_id
        self._batch_size = batch_size
        self._lease_seconds = lease_seconds
        self._max_attempts = max_attempts
        self._max_retry_delay = max_retry_delay_seconds
        self._window = timedelta(hours=window_hours)
        self._whatsapp_enabled = whatsapp_enabled

    async def run_once(self) -> None:
        now = datetime.now(timezone.utc)
        events = await self._repository.claim_batch(
            now=now, batch_size=self._batch_size, lease_seconds=self._lease_seconds
        )
        await asyncio.gather(*(self._process(event) for event in events))
        NOTIFICATION_WORKER_HEALTH.labels("processor").set(1)

    async def _process(self, event: NotificationEvent) -> None:
        started = asyncio.get_running_loop().time()
        outcome = "dispatched"
        try:
            if event.preferred_channel == ChannelName.DEVELOPMENT_HTTP:
                outcome = "suppressed"
                await self._repository.suppress(
                    event.id, "web_push_not_supported", datetime.now(timezone.utc)
                )
                return
            target = await self._repository.resolve_channel(event)
            if target is None or not self._whatsapp_enabled:
                outcome = "suppressed"
                await self._repository.suppress(
                    event.id, "no_supported_channel", datetime.now(timezone.utc)
                )
                return
            payload = event.order_payload()
            template, fell_back = self._templates.get(
                event.notification_type, event.locale
            )
            if fell_back:
                NOTIFICATION_LOCALE_FALLBACK.labels(target.channel.value).inc()
            body, variables = self._templates.render(template, payload)
            now = datetime.now(timezone.utc)
            last_inbound = await self._channel_repository.conversation_last_inbound(
                target.conversation_id
            )
            inside_window = (
                last_inbound is not None and now - last_inbound <= self._window
            )
            if not inside_window and template.provider_content_sid is None:
                raise NotificationTemplateError(
                    "Approved provider template is unavailable."
                )
            mode = (
                NotificationContentMode.TEXT
                if inside_window
                else NotificationContentMode.TEMPLATE
            )
            await self._repository.dispatch_to_channel(
                event,
                target,
                template,
                body=body,
                sender_id=self._sender_id,
                content_mode=mode,
                content_variables=variables,
                now=now,
            )
        except (NotificationTemplateError, ValidationError, ValueError):
            outcome = "dead_letter"
            await self._repository.mark_failed(
                event.id,
                status=NotificationStatus.DEAD_LETTER,
                error_code="invalid_notification_contract",
                next_attempt_at=None,
            )
            logger.exception("Notification contract processing failed")
        except (asyncpg.PostgresError, RuntimeError):
            retry = event.attempt_count < self._max_attempts
            outcome = "retryable" if retry else "dead_letter"
            await self._repository.mark_failed(
                event.id,
                status=NotificationStatus.RETRYABLE
                if retry
                else NotificationStatus.DEAD_LETTER,
                error_code="temporary_processing_failure"
                if retry
                else "attempts_exhausted",
                next_attempt_at=self._next_attempt(event.attempt_count)
                if retry
                else None,
            )
            logger.exception("Notification processing failed")
        finally:
            NOTIFICATION_EVENTS.labels(event.notification_type.value, outcome).inc()
            NOTIFICATION_LATENCY.labels(outcome).observe(
                asyncio.get_running_loop().time() - started
            )

    def _next_attempt(self, attempt: int) -> datetime:
        delay = min(float(self._max_retry_delay), 2 ** max(0, attempt - 1))
        return datetime.now(timezone.utc) + timedelta(
            seconds=delay * random.uniform(0.8, 1.2)
        )

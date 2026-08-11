from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone

from app.observability import INBOX_LATENCY, OUTBOUND, RETRIES, WORKER_HEALTH
from channels.models import InboundMessage, MessageKind, OutboundMessage, OutboundStatus
from channels.providers import OutboundMessageProvider
from commerce.models import ChannelName
from infrastructure.channels.twilio import (
    TwilioAmbiguousSendError,
    TwilioPermanentSendError,
    TwilioRetryableSendError,
)
from infrastructure.database.repositories import PostgresChannelRepository
from runtime.contracts import ConversationState, CustomerChannelContext, Message
from runtime.domain.commerce_runtime import CommerceRuntime

logger = logging.getLogger(__name__)
CHANNEL = ChannelName.TWILIO_WHATSAPP.value


class PeriodicChannelWorker:
    def __init__(self, interval_seconds: float, worker_name: str) -> None:
        self._interval = interval_seconds
        self._worker_name = worker_name
        self._task: asyncio.Task[None] | None = None
        self.last_success_at: datetime | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def _run(self) -> None:
        while True:
            try:
                await self.run_once()
                self.last_success_at = datetime.now(timezone.utc)
                WORKER_HEALTH.labels(CHANNEL, self._worker_name).set(1)
            except Exception:
                WORKER_HEALTH.labels(CHANNEL, self._worker_name).set(0)
                logger.exception(
                    "Channel worker iteration failed",
                    extra={"worker": self._worker_name},
                )
            await asyncio.sleep(self._interval)

    async def run_once(self) -> None:
        raise NotImplementedError


class ChannelInboundProcessor(PeriodicChannelWorker):
    def __init__(
        self,
        repository: PostgresChannelRepository,
        runtime: CommerceRuntime,
        sender_id: str,
        batch_size: int,
        lease_seconds: int,
        max_attempts: int,
        interval_seconds: float,
    ) -> None:
        super().__init__(interval_seconds, "inbound")
        self._repository = repository
        self._runtime = runtime
        self._sender_id = sender_id
        self._batch_size = batch_size
        self._lease_seconds = lease_seconds
        self._max_attempts = max_attempts

    async def run_once(self) -> None:
        now = datetime.now(timezone.utc)
        messages = await self._repository.claim_inbound_batch(
            self._batch_size, now, self._lease_seconds
        )
        await asyncio.gather(*(self._process(message) for message in messages))

    async def _process(self, inbound: InboundMessage) -> None:
        started = asyncio.get_running_loop().time()
        try:
            async with self._repository.conversation_lock(
                inbound.tenant_id, inbound.conversation_id
            ) as acquired:
                if not acquired:
                    raise RuntimeError("conversation_busy")
                if inbound.message_kind == MessageKind.UNSUPPORTED:
                    reply = "Sorry, I can currently help only with text messages."
                else:
                    conversation = ConversationState(
                        conversation_id=inbound.conversation_id
                    )
                    conversation.add_message(
                        Message.user(inbound.body).model_copy(update={"id": inbound.id})
                    )
                    context = CustomerChannelContext(
                        tenant_id=inbound.tenant_id,
                        conversation_id=inbound.conversation_id,
                        channel=inbound.channel,
                        channel_customer_id=inbound.sender_id,
                        request_id=f"twilio-whatsapp:{inbound.provider_message_id}",
                    )
                    result = await self._runtime.chat(conversation, context)
                    reply = (
                        result.latest_message.content if result.latest_message else ""
                    )
                    if not reply:
                        raise RuntimeError("empty_agent_response")
                await self._repository.complete_inbound(
                    inbound, reply, self._sender_id, datetime.now(timezone.utc)
                )
            INBOX_LATENCY.labels(CHANNEL, "processed").observe(
                asyncio.get_running_loop().time() - started
            )
        except Exception:
            retry = inbound.attempt_count < self._max_attempts
            await self._repository.fail_inbound(
                inbound.id,
                retry=retry,
                error_code="agent_unavailable" if retry else "attempts_exhausted",
                next_attempt_at=_next_attempt(inbound.attempt_count),
            )
            RETRIES.labels(
                CHANNEL, "inbound", "retry" if retry else "dead_letter"
            ).inc()
            logger.exception(
                "Inbound channel message processing failed",
                extra={"inbound_id": str(inbound.id)},
            )


class ChannelOutboundDispatcher(PeriodicChannelWorker):
    def __init__(
        self,
        repository: PostgresChannelRepository,
        provider: OutboundMessageProvider,
        status_callback_url: str,
        batch_size: int,
        lease_seconds: int,
        max_attempts: int,
        interval_seconds: float,
        window_hours: int,
    ) -> None:
        super().__init__(interval_seconds, "outbound")
        self._repository = repository
        self._provider = provider
        self._status_callback_url = status_callback_url
        self._batch_size = batch_size
        self._lease_seconds = lease_seconds
        self._max_attempts = max_attempts
        self._window = timedelta(hours=window_hours)

    async def run_once(self) -> None:
        now = datetime.now(timezone.utc)
        messages = await self._repository.claim_outbound_batch(
            self._batch_size, now, self._lease_seconds
        )
        await asyncio.gather(*(self._dispatch(message) for message in messages))

    async def _dispatch(self, outbound: OutboundMessage) -> None:
        now = datetime.now(timezone.utc)
        last_inbound = await self._repository.conversation_last_inbound(
            outbound.conversation_id
        )
        if last_inbound is None or now - last_inbound > self._window:
            await self._repository.fail_outbound(
                outbound.id,
                OutboundStatus.TEMPLATE_REQUIRED,
                "customer_service_window_closed",
                now,
            )
            OUTBOUND.labels(CHANNEL, "template_required").inc()
            return
        try:
            result = await self._provider.send_text(
                outbound.recipient_id,
                outbound.body,
                outbound.id,
                self._status_callback_url,
            )
            await self._repository.accept_outbound(
                outbound.id, result.provider_message_id, now
            )
            OUTBOUND.labels(CHANNEL, "accepted").inc()
        except TwilioAmbiguousSendError:
            await self._repository.fail_outbound(
                outbound.id, OutboundStatus.AMBIGUOUS, "ambiguous_send", now
            )
            OUTBOUND.labels(CHANNEL, "ambiguous").inc()
        except TwilioPermanentSendError:
            await self._repository.fail_outbound(
                outbound.id, OutboundStatus.FAILED, "permanent_provider_error", now
            )
            OUTBOUND.labels(CHANNEL, "failed").inc()
        except TwilioRetryableSendError:
            retry = outbound.attempt_count < self._max_attempts
            await self._repository.fail_outbound(
                outbound.id,
                OutboundStatus.RETRYABLE if retry else OutboundStatus.DEAD_LETTER,
                "temporary_provider_error" if retry else "attempts_exhausted",
                now,
                _next_attempt(outbound.attempt_count),
            )
            RETRIES.labels(
                CHANNEL, "outbound", "retry" if retry else "dead_letter"
            ).inc()


def _next_attempt(attempt: int) -> datetime:
    delay = min(300.0, 2 ** max(0, attempt - 1))
    delay *= random.uniform(0.8, 1.2)
    return datetime.now(timezone.utc) + timedelta(seconds=delay)

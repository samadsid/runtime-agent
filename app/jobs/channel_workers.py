from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone

from app.observability import (
    AMBIGUOUS_SENDS,
    INBOX_LATENCY,
    OUTBOUND,
    OUTBOUND_PRESENTATION,
    RETRIES,
    WORKER_HEALTH,
)
from channels.models import (
    ApprovedTemplateMessage,
    InboundMessage,
    MessageKind,
    OutboundMessage,
    OutboundStatus,
    WhatsAppProviderName,
)
from channels.providers import (
    AmbiguousSendError,
    OutboundMessageProvider,
    PermanentSendError,
    RetryableSendError,
    TypingIndicatorProvider,
)
from channels.templates import WhatsAppTemplateRegistry
from commerce.models import ChannelName, NotificationContentMode
from commerce.services import NotificationTemplateError, NotificationTemplateRegistry
from infrastructure.database.repositories import PostgresChannelRepository
from runtime.contracts import (
    ApprovedResponseFragment,
    ConversationState,
    CustomerChannelContext,
    ExecutionStatus,
    GeneratedExecutionOutcome,
    Message,
    TrustedInboundMessageContext,
)
from runtime.domain.commerce_runtime import CommerceRuntime
from runtime.responses import (
    ResponseGenerator,
    WhatsAppFormattingError,
    WhatsAppResponseFormatter,
)

logger = logging.getLogger(__name__)
CHANNEL = ChannelName.WHATSAPP.value


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
        provider_name: WhatsAppProviderName = WhatsAppProviderName.TWILIO,
        response_generator: ResponseGenerator | None = None,
        returning_inactivity_hours: int = 24,
        typing_provider: TypingIndicatorProvider | None = None,
        typing_refresh_seconds: float = 20.0,
    ) -> None:
        super().__init__(interval_seconds, "inbound")
        if typing_refresh_seconds <= 0:
            raise ValueError("typing_refresh_seconds must be positive")
        self._repository = repository
        self._runtime = runtime
        self._sender_id = sender_id
        self._batch_size = batch_size
        self._lease_seconds = lease_seconds
        self._max_attempts = max_attempts
        self._provider_name = provider_name
        self._response_generator = response_generator
        self._returning_inactivity = timedelta(hours=returning_inactivity_hours)
        self._typing_provider = typing_provider
        self._typing_refresh_seconds = typing_refresh_seconds

    async def run_once(self) -> None:
        now = datetime.now(timezone.utc)
        messages = await self._repository.claim_inbound_batch(
            self._batch_size, now, self._lease_seconds, self._provider_name
        )
        await asyncio.gather(*(self._process(message) for message in messages))

    async def _process(self, inbound: InboundMessage) -> None:
        started = asyncio.get_running_loop().time()
        typing_task: asyncio.Task[None] | None = None
        try:
            async with self._repository.conversation_lock(
                inbound.tenant_id, inbound.conversation_id
            ) as acquired:
                if not acquired:
                    raise RuntimeError("conversation_busy")
                if self._typing_provider is not None:
                    typing_task = asyncio.create_task(
                        self._refresh_typing(inbound.provider_message_id)
                    )
                    await asyncio.sleep(0)
                if inbound.message_kind == MessageKind.UNSUPPORTED:
                    approved = (
                        "That location message is invalid or unsupported. Please send a standard one-time WhatsApp Location attachment."
                        if inbound.body == "[invalid-location]"
                        else "Sorry, I can currently help only with text messages and standard location attachments."
                    )
                    if self._response_generator is None:
                        reply, _ = WhatsAppResponseFormatter.normalize(approved)
                        WhatsAppResponseFormatter.validate_structure(reply)
                    else:
                        language_signal = await self._repository.latest_text_body(
                            inbound.conversation_id, exclude_id=inbound.id
                        )
                        reply = await self._response_generator.generate(
                            GeneratedExecutionOutcome(
                                status=ExecutionStatus.SUCCESS,
                                fragments=(
                                    ApprovedResponseFragment(
                                        id=(
                                            "location-message-invalid"
                                            if inbound.body == "[invalid-location]"
                                            else "unsupported-message-limitation"
                                        ),
                                        text=approved,
                                    ),
                                ),
                            ),
                            language_signal or "",
                        )
                else:
                    previous_inbound_at = await self._repository.previous_inbound_at(
                        inbound.conversation_id, exclude_id=inbound.id
                    )
                    conversation = ConversationState(
                        conversation_id=inbound.conversation_id
                    )
                    conversation.add_message(
                        Message.user(
                            inbound.body
                            if inbound.message_kind is MessageKind.TEXT
                            else "Customer shared a delivery location."
                        ).model_copy(update={"id": inbound.id})
                    )
                    context = CustomerChannelContext(
                        tenant_id=inbound.tenant_id,
                        conversation_id=inbound.conversation_id,
                        channel=inbound.channel,
                        channel_customer_id=inbound.sender_id,
                        request_id=(
                            f"{'meta' if inbound.provider == WhatsAppProviderName.META_CLOUD else 'twilio'}-"
                            f"whatsapp:{inbound.provider_message_id}"
                        ),
                        conversation_entry=(
                            previous_inbound_at is None
                            or inbound.received_at - previous_inbound_at
                            >= self._returning_inactivity
                        ),
                        inbound_message=TrustedInboundMessageContext(
                            inbound_message_id=inbound.id,
                            request_id=(
                                f"{'meta' if inbound.provider == WhatsAppProviderName.META_CLOUD else 'twilio'}-"
                                f"whatsapp:{inbound.provider_message_id}"
                            ),
                            message_kind=inbound.message_kind,
                            location=inbound.location,
                        ),
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
        finally:
            if typing_task is not None:
                typing_task.cancel()
                try:
                    await typing_task
                except asyncio.CancelledError:
                    pass

    async def _refresh_typing(self, inbound_provider_message_id: str) -> None:
        assert self._typing_provider is not None
        while True:
            try:
                await self._typing_provider.send_typing(inbound_provider_message_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning(
                    "WhatsApp typing indicator failed",
                    extra={"provider": self._provider_name.value},
                    exc_info=True,
                )
            await asyncio.sleep(self._typing_refresh_seconds)


class ChannelOutboundDispatcher(PeriodicChannelWorker):
    def __init__(
        self,
        repository: PostgresChannelRepository,
        provider: OutboundMessageProvider,
        batch_size: int,
        lease_seconds: int,
        max_attempts: int,
        interval_seconds: float,
        window_hours: int,
        notification_templates: NotificationTemplateRegistry | None = None,
        provider_templates: WhatsAppTemplateRegistry | None = None,
        provider_name: WhatsAppProviderName = WhatsAppProviderName.TWILIO,
        max_text_chars: int | None = None,
    ) -> None:
        super().__init__(interval_seconds, "outbound")
        self._repository = repository
        self._provider = provider
        self._batch_size = batch_size
        self._lease_seconds = lease_seconds
        self._max_attempts = max_attempts
        self._window = timedelta(hours=window_hours)
        self._notification_templates = notification_templates
        self._provider_templates = provider_templates
        self._provider_name = provider_name
        self._max_text_chars = max_text_chars

    async def run_once(self) -> None:
        now = datetime.now(timezone.utc)
        messages = await self._repository.claim_outbound_batch(
            self._batch_size, now, self._lease_seconds, self._provider_name
        )
        await asyncio.gather(*(self._dispatch(message) for message in messages))

    async def _dispatch(self, outbound: OutboundMessage) -> None:
        now = datetime.now(timezone.utc)
        last_inbound = await self._repository.conversation_last_inbound(
            outbound.conversation_id
        )
        try:
            outside_window = last_inbound is None or now - last_inbound > self._window
            if outside_window and outbound.content_mode == NotificationContentMode.TEXT:
                if (
                    outbound.source_inbound_id is not None
                    or self._notification_templates is None
                    or self._provider_templates is None
                ):
                    await self._repository.fail_outbound(
                        outbound.id,
                        OutboundStatus.TEMPLATE_REQUIRED,
                        "customer_service_window_closed",
                        now,
                    )
                    OUTBOUND.labels(CHANNEL, "template_required").inc()
                    return
                event = await self._repository.notification_for_outbound(outbound.id)
                if event is None:
                    raise PermanentSendError("missing_notification_delivery")
                template, _ = self._notification_templates.get(
                    event.notification_type, event.locale
                )
                _, variables = self._notification_templates.render(
                    template, event.order_payload()
                )
                provider_template = self._provider_templates.get(
                    template, self._provider_name
                )
                outbound = await self._repository.upgrade_notification_to_template(
                    outbound.id,
                    template_key=template.key,
                    template_name=provider_template.name,
                    template_language=provider_template.language,
                    content_variables=variables,
                    now=now,
                )
            if outbound.content_mode == NotificationContentMode.TEMPLATE:
                OUTBOUND_PRESENTATION.labels("template", "attempted").inc()
                template_name = outbound.template_name or outbound.content_sid
                if template_name is None or outbound.content_variables is None:
                    raise PermanentSendError("incomplete_content_template")
                await self._repository.mark_send_started(outbound.id, now)
                result = await self._provider.send_template(
                    outbound.recipient_id,
                    ApprovedTemplateMessage(
                        key=outbound.template_key or template_name,
                        name=template_name,
                        language=outbound.template_language,
                        parameters={
                            str(key): str(value)
                            for key, value in outbound.content_variables.items()
                        },
                    ),
                    outbound.id,
                )
            else:
                if outbound.body is None:
                    raise PermanentSendError("missing_text_body")
                try:
                    WhatsAppResponseFormatter.validate_structure(outbound.body)
                except WhatsAppFormattingError:
                    OUTBOUND_PRESENTATION.labels(
                        "free_form", "structure_rejected"
                    ).inc()
                    await self._repository.fail_outbound(
                        outbound.id,
                        OutboundStatus.FAILED,
                        "invalid_text_structure",
                        now,
                    )
                    return
                if (
                    self._max_text_chars is not None
                    and len(outbound.body) > self._max_text_chars
                ):
                    OUTBOUND_PRESENTATION.labels("free_form", "size_rejected").inc()
                    await self._repository.fail_outbound(
                        outbound.id,
                        OutboundStatus.FAILED,
                        "body_too_long",
                        now,
                    )
                    return
                OUTBOUND_PRESENTATION.labels("free_form", "attempted").inc()
                await self._repository.mark_send_started(outbound.id, now)
                result = await self._provider.send_text(
                    outbound.recipient_id,
                    outbound.body,
                    outbound.id,
                )
            await self._repository.accept_outbound(
                outbound.id, result.provider_message_id, now
            )
            OUTBOUND.labels(CHANNEL, "accepted").inc()
        except AmbiguousSendError as error:
            await self._repository.fail_outbound(
                outbound.id,
                OutboundStatus.AMBIGUOUS,
                (str(error) or "ambiguous_send")[:64],
                now,
            )
            OUTBOUND.labels(CHANNEL, "ambiguous").inc()
            AMBIGUOUS_SENDS.labels(CHANNEL).inc()
        except PermanentSendError as error:
            await self._repository.fail_outbound(
                outbound.id,
                OutboundStatus.FAILED,
                (str(error) or "permanent_provider_error")[:64],
                now,
            )
            OUTBOUND.labels(CHANNEL, "failed").inc()
        except (NotificationTemplateError, ValueError):
            await self._repository.fail_outbound(
                outbound.id, OutboundStatus.FAILED, "invalid_template_contract", now
            )
            OUTBOUND.labels(CHANNEL, "failed").inc()
        except RetryableSendError as error:
            retry = outbound.attempt_count < self._max_attempts
            await self._repository.fail_outbound(
                outbound.id,
                OutboundStatus.RETRYABLE if retry else OutboundStatus.DEAD_LETTER,
                (str(error) or "temporary_provider_error")[:64]
                if retry
                else "attempts_exhausted",
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

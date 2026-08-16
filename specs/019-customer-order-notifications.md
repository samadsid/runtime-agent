Customer Order Notifications Specification

1. Purpose

Notify customers reliably when important order or payment state changes occur:

ORDER_CONFIRMED
ORDER_PREPARING
ORDER_OUT_FOR_DELIVERY
ORDER_DELIVERED
ORDER_CANCELLED
PAYMENT_PENDING
PAYMENT_CONFIRMED
PAYMENT_FAILED
PAYMENT_EXPIRED
PAYMENT_REFUNDED

The first implementation must support cash-on-delivery order lifecycle notifications.Payment notification contracts are defined now but remain dormant until the productionpayment-provider milestone is enabled.

Notifications are transactional consequences of authoritative business state changes.They are not planner decisions, LangGraph messages, or best-effort calls made inside anorder transaction.

2. Prerequisites

Order creation and immutable order snapshots.

Fulfilment transitions and order-status history from specification 006.

Customer cancellation from specification 007.

Saved customer/channel context where available.

Twilio WhatsApp channel inbox/outbox and delivery tracking from specification 014.

Runtime request idempotency and PostgreSQL worker row claiming.

Alembic-managed application schema.

Health, metrics, structured logging, retries, and dead-letter conventions.

3. Goals

Never commit a customer-visible order transition without durably recording itsnotification intent.

Deliver each logical notification at least once to the selected channel while makingduplicate generation and dispatch harmless.

Keep business transactions independent of Twilio or any other provider's availability.

Use deterministic, reviewed templates rather than an LLM for proactive messages.

Support free-form WhatsApp messages inside the customer-service window and approvedcontent templates outside it.

Track generation, dispatch, provider acceptance, delivery, failure, and dead-letterstates separately.

Protect customer PII and tenant isolation.

Permit future web, email, SMS, push, and payment notifications without coupling orderservices to a provider.

Preserve the existing customer graph unchanged.

4. Non-goals

Marketing, promotions, recommendations, abandoned-cart reminders, or campaigns.

OTP delivery or phone ownership verification.

Staff authentication or fulfilment UI.

Live driver tracking, delivery ETA calculation, or maps.

Letting the planner decide whether an authoritative status notification exists.

Translating proactive messages dynamically with an LLM.

Exactly-once delivery over external providers.

Building a general enterprise event bus in this milestone.

Requiring Kafka, RabbitMQ, or another broker for the first implementation.

5. Frozen Architecture

The conversational graph remains:

Planner -> Execute -> Response -> END

Notifications use a separate deterministic pipeline:

Order/payment transaction
    -> update authoritative state
    -> append status history
    -> insert notification outbox event
    -> COMMIT

Notification processor
    -> claim outbox event
    -> resolve channel/template/locale
    -> create channel outbound message
    -> mark event dispatched

Channel dispatcher
    -> provider API
    -> provider message ID
    -> delivery status callbacks

Rules:

Do not add a notification LangGraph node.

Order/payment services never call Twilio, email, SMS, or an LLM.

Notification workers never change order or payment state.

Provider status callbacks never change order status.

The order/payment state change, history record, and notification outbox insertion arecommitted in one PostgreSQL transaction.

The notification event and channel outbound message are separate durable records withseparate lifecycle states.

Existing conversational replies continue through the Response Node; proactivenotifications use deterministic notification templates.

6. Terminology

Business event: an authoritative order or payment transition eligible for acustomer notification.

Notification outbox event: durable intent to notify a customer about one businessevent.

Notification message: channel-neutral rendered content produced from a reviewedtemplate and approved event data.

Channel outbound message: provider-specific delivery record used by the existingoutbound dispatcher.

Delivery event: provider callback such as accepted, sent, delivered, read, failed,or undelivered.

Logical notification key: stable idempotency key identifying one notificationtype for one source business transition.

7. Notification Event Types

7.1 Order events enabled initially

Event

Trigger

Customer meaning

ORDER_CONFIRMED

Order becomes CONFIRMED

Order accepted/confirmed

ORDER_PREPARING

CONFIRMED -> PREPARING

Preparation has started

ORDER_OUT_FOR_DELIVERY

PREPARING -> OUT_FOR_DELIVERY

Order has left for delivery

ORDER_DELIVERED

OUT_FOR_DELIVERY -> DELIVERED

Order marked delivered

ORDER_CANCELLED

Allowed transition to CANCELLED

Order cancelled

7.2 Payment events defined but feature-gated

Event

Trigger

PAYMENT_PENDING

Payment attempt enters pending/customer-action state

PAYMENT_CONFIRMED

Verified provider event confirms payment

PAYMENT_FAILED

Authoritative provider failure

PAYMENT_EXPIRED

Pending attempt expires under payment policy

PAYMENT_REFUNDED

Verified full refund succeeds

Do not emit payment notifications before online payments are enabled. Cash on deliverymust not be described as paid merely because the order is confirmed or delivered.

7.3 Repeated/no-op transitions

Repeating the current order/payment status is an idempotent no-op and must not create anew notification event. A notification is generated only for a newly committed sourcetransition/history row.

8. Source Event Identity

Every notification-producing business transition must have a durable source identity.For order events, use the exact order_status_history.id. For payment events, use thedurable payment transition/event identity defined by the payment specification.

Logical uniqueness:

(tenant_id, source_type, source_id, notification_type)

Examples:

(tenant A, ORDER_STATUS_HISTORY, history UUID, ORDER_PREPARING)
(tenant A, PAYMENT_EVENT, event UUID, PAYMENT_CONFIRMED)

Never use timestamp, message body, customer phone, provider message SID, or an LLMrequest as the logical notification key.

9. PostgreSQL Schema

Create application-owned tables through Alembic.

9.1 notification_outbox

Column

Type

Rule

id

UUID

Primary key

tenant_id

UUID

Required tenant boundary

notification_type

text

Required supported enum value

source_type

text

ORDER_STATUS_HISTORY or future supported source

source_id

UUID

Durable source transition/event ID

order_id

UUID

Nullable for non-order future notifications; FK when present

customer_channel_id

UUID

Nullable durable channel identity reference

preferred_channel

text

Nullable normalized channel captured at event creation

locale

text

Nullable safe locale/style key, not arbitrary prompt text

payload

jsonb

Versioned approved event data only

payload_version

integer

Required, starts at 1

status

text

Processing status

attempt_count

integer

Required, starts at 0

available_at

timestamptz

Earliest claim time

lease_expires_at

timestamptz

Nullable claim lease

last_error_code

text

Nullable bounded internal category

created_at

timestamptz

Required

processed_at

timestamptz

Nullable

Statuses:

PENDING -> PROCESSING -> DISPATCHED
                    \-> RETRYABLE -> PROCESSING
                    \-> DEAD_LETTER
                    \-> SUPPRESSED

Constraints/indexes:

UNIQUE (tenant_id, source_type, source_id, notification_type)
INDEX (status, available_at, created_at)
INDEX (tenant_id, order_id, created_at)
CHECK (attempt_count >= 0)

9.2 notification_deliveries

This table connects one logical notification to one channel outbound message.

Column

Type

Rule

id

UUID

Primary key

notification_id

UUID

FK to notification_outbox

channel

text

Normalized delivery channel

channel_outbound_message_id

UUID

FK to existing outbound record

template_key

text

Internal template identifier

template_version

integer

Required

created_at

timestamptz

Required

Constraints:

UNIQUE (notification_id, channel)
UNIQUE (channel_outbound_message_id)

Provider acceptance/delivery state remains in the existing channel outbound anddelivery-event tables. Do not duplicate Twilio callback history here.

10. Event Payload

The payload contains immutable, approved business values required for rendering. It isnot a complete order serialization.

Example:

{
  "version": 1,
  "order_reference": "MU-2026-000123",
  "order_status": "OUT_FOR_DELIVERY",
  "payment_method": "CASH_ON_DELIVERY",
  "currency": "INR",
  "total_amount": "1600.00",
  "occurred_at": "2026-08-13T09:30:00Z"
}

Rules:

Store exact order reference/status and only values approved for notification.

Monetary values use strings/decimals without floating-point conversion.

Do not store full phone number, delivery address, internal reason, staff actor ID,inventory balance, provider secret, or planner/conversation transcript in payload.

Do not use mutable product/profile data as the only source for a historicalnotification.

Version every payload and template contract.

Payload validation must occur before insertion.

11. Atomic Event Creation

Extend order confirmation, fulfilment transition, customer cancellation, and laterpayment transactions.

For a valid new order transition, the transaction must:

lock and validate the order;

apply inventory/reservation effects where required;

update the authoritative order state;

insert the exact status-history row;

insert one notification outbox row referencing that history ID;

commit all changes together.

If outbox insertion fails, roll back the state transition. There must be no committednew status without its required notification intent.

An outbox row does not guarantee provider delivery; it guarantees the delivery intentsurvives process/provider failure.

12. Repository Contracts

Add domain/application interfaces using project naming conventions:

class NotificationOutboxRepository(Protocol):
    async def append_in_transaction(
        self,
        connection: TransactionConnection,
        event: NewNotificationEvent,
    ) -> NotificationEvent: ...

    async def claim_batch(
        self,
        *,
        now: datetime,
        batch_size: int,
        lease_seconds: int,
    ) -> tuple[NotificationEvent, ...]: ...

    async def mark_dispatched(
        self,
        notification_id: UUID,
        delivery: NotificationDelivery,
        processed_at: datetime,
    ) -> None: ...

    async def mark_failed(
        self,
        notification_id: UUID,
        *,
        retry: bool,
        error_code: NotificationErrorCode,
        next_attempt_at: datetime | None,
    ) -> None: ...

    async def suppress(
        self,
        notification_id: UUID,
        reason: NotificationSuppressionReason,
    ) -> None: ...

Infrastructure implementations return domain models, not asyncpg.Record objects.

The exact transaction-connection abstraction must follow the existing repository unitof work. Do not open a second connection to append the event after the order transaction.

13. Notification Processor

Add a periodic notification processor following the existing worker pattern:

class NotificationOutboxProcessor(PeriodicWorker):
    async def run_once(self) -> None:
        events = await repository.claim_batch(...)
        await asyncio.gather(*(self._process(event) for event in events))

For each event:

validate payload version and notification type;

resolve the snapshotted/preferred supported customer channel;

select locale and deterministic template;

render a channel-neutral message;

atomically create or reuse the channel outbound row and notification delivery link;

mark the notification DISPATCHED; or

classify failure as retryable, permanent/dead-letter, or suppressed.

The worker does not call the channel provider directly. Existing outbound dispatchersown provider delivery.

Use FOR UPDATE SKIP LOCKED or the established lease claim pattern so multiple workerinstances do not process the same event concurrently.

14. Two Durable Outbox Layers

The design intentionally separates:

notification_outbox: business intent and template/channel resolution;

existing channel_outbound_messages: provider delivery and callback lifecycle.

This permits:

rerouting notification policy without changing order history;

provider retries without rerendering business events;

channel delivery metrics separate from notification-generation metrics; and

future channels sharing the same business notification event.

Creating the channel outbound row, notification-delivery link, and marking thenotification DISPATCHED must happen atomically. A crash cannot mark a notificationdispatched without a durable outbound message, or create multiple outbound rows for thesame notification/channel.

15. Channel Resolution

The order should retain or reference the trusted customer channel context necessary forfuture delivery:

class OrderNotificationTarget(BaseModel):
    channel: ChannelName
    channel_customer_id: str

Prefer a durable channel identity reference rather than duplicating a raw destinationin every event. Resolve the destination under the same tenant.

Rules:

Use the channel through which the order was placed unless an authenticated futurepreference policy changes it.

Do not use an LLM-supplied destination.

Do not use saved phone number as a WhatsApp destination merely because it resemblesone; use the trusted channel identity.

A customer-provided but unverified phone is not a verified notification channel.

Never send an order notification to a different tenant's channel identity.

If no supported durable outbound target exists, mark the event SUPPRESSED with abounded reason such as no_supported_channel; do not retry forever.

16. Web Chat Behavior

The current request/response web frontend cannot receive proactive messages while thecustomer is offline.

For web-origin orders in this milestone:

always retain notification events in PostgreSQL;

deliver through a trusted linked supported channel when available;

otherwise suppress provider delivery with web_push_not_supported; and

expose the latest authoritative status when the customer returns through existingorder-details/status capabilities.

WebSocket/SSE, browser push, notification center, and polling endpoints are deferred.

17. Language and Template Selection

Proactive notifications must not use the Response Node or an LLM. Use reviewed,versioned deterministic templates.

Locale sources, in priority order:

explicitly saved customer notification locale when available;

safe channel/conversation locale projection captured before event creation;

tenant default locale.

Do not store arbitrary latest message style text in the event. Map to a bounded localeor template style key such as:

en-IN
hi-IN
hi-Latn-IN

If a locale template is missing, use the configured tenant fallback and record a safefallback metric. Product/order references and numeric values remain exact.

18. Template Registry

Define templates in code/configuration or a reviewed database registry outside prompts:

class NotificationTemplate(BaseModel):
    key: str
    version: int
    notification_type: NotificationType
    channel: ChannelName
    locale: str
    body_template: str
    provider_content_sid: str | None = None

Template rules:

Templates use a strict allowlist of payload placeholders.

Render with a strict engine that fails on missing/unknown variables.

Never evaluate executable expressions.

Version template changes.

Keep provider identifiers in environment/database configuration, never prompts.

Validate required provider template mappings at startup when proactive WhatsApp isenabled.

Never include raw internal failure or cancellation reasons unless explicitly approvedfor customers.

19. Initial Message Meanings

Suggested deterministic meanings:

19.1 Confirmed

Your order {order_reference} has been confirmed. Payment method: CASH_ON_DELIVERY.

Do not say payment was received for cash on delivery.

19.2 Preparing

Your order {order_reference} is now being prepared.

19.3 Out for delivery

Your order {order_reference} is out for delivery.

Do not invent an ETA, driver name, or phone number.

19.4 Delivered

Your order {order_reference} has been marked delivered.

19.5 Cancelled

Your order {order_reference} has been cancelled.

Do not promise refund timing unless a verified refund event and approved template exist.

20. WhatsApp Service Window and Templates

For Twilio WhatsApp:

If the most recent customer inbound message is inside the configured customer-servicewindow, the outbound dispatcher may send the rendered free-form text according tochannel policy.

Outside the window, use the approved Twilio Content Template mapped to notificationtype and locale.

Do not mark a notification TEMPLATE_REQUIRED and stop if an approved configuredtemplate exists; render the provider template request.

If the required approved template mapping is unavailable, classify it as a permanentconfiguration failure/dead-letter or suppression according to deployment policy.

ContentSid and ContentVariables must be supplied together for template sends.

For free-form sends, use Body and omit content-template fields.

Provider template variables come only from the validated event payload.

Extend the provider abstraction:

async def send_text(...): ...

async def send_template(
    recipient_id: str,
    content_sid: str,
    content_variables: Mapping[str, str],
    idempotency_key: UUID,
    status_callback_url: str,
) -> ProviderMessageResult: ...

The channel dispatcher, not the notification processor, makes the final window-awareprovider call using durable outbound message mode and template fields.

21. Channel Outbound Extension

Extend the existing outbound record with a mutually exclusive content mode:

TEXT: body required; template fields absent
TEMPLATE: content_sid and content_variables required; body optional presentation copy

Validation must reject:

content_variables without content_sid;

both incomplete text and incomplete template content;

arbitrary template variables not produced by the registry; and

invalid provider content SID formats when Twilio is enabled.

This explicitly prevents the earlier 21654 ContentSid Required class of malformedrequest.

22. Retry and Failure Classification

Notification processing retries only transient internal failures:

temporary database/pool failure;

transient channel-outbox persistence conflict;

temporarily unavailable template registry dependency, if externalized.

Channel dispatch follows provider-specific retry rules already defined by specification014.

Use bounded exponential backoff with jitter and configured attempt limits. Do not retry:

missing/unsupported payload version;

unsupported notification type;

no supported customer channel;

invalid permanent destination;

missing required approved template mapping after configuration validation;

tenant isolation violation; or

malformed approved data.

Do not store raw provider error messages as public error codes. Preserve detailed safediagnostics in protected structured logs where allowed.

23. Delivery Status

Provider callbacks update only the channel outbound lifecycle:

PENDING -> SENDING -> ACCEPTED -> SENT -> DELIVERED -> READ
                           \-> FAILED / AMBIGUOUS / DEAD_LETTER

Rules:

Duplicate callbacks are idempotent.

Status cannot regress from terminal/higher states.

Unknown outbound provider IDs are recorded safely for diagnostics without creating anotification.

Delivery failure does not roll back order/payment status.

A delivered notification does not prove the customer read or accepted the underlyingorder status.

24. Preferences and Mandatory Transactional Events

This milestone treats order confirmation, fulfilment, cancellation, and enabled paymentstate messages as transactional service notifications, not marketing.

Allow only channel/locale delivery preferences that do not suppress legally oroperationally required messages under applicable policy. A full customer preference andconsent center is deferred.

Do not reuse transactional notification consent or channel identifiers for promotions.

25. Configuration

Add environment-backed settings using project naming conventions:

CUSTOMER_NOTIFICATIONS_ENABLED=true
NOTIFICATION_PROCESSOR_ENABLED=true
NOTIFICATION_PROCESSOR_INTERVAL_SECONDS=1
NOTIFICATION_PROCESSOR_BATCH_SIZE=20
NOTIFICATION_PROCESSOR_LEASE_SECONDS=120
NOTIFICATION_PROCESSOR_MAX_ATTEMPTS=5
NOTIFICATION_RETRY_MAX_DELAY_SECONDS=300
NOTIFICATION_DEFAULT_LOCALE=en-IN
NOTIFICATION_TEMPLATE_REGISTRY_VERSION=1

Add per-type/locale/channel Twilio Content SID mappings through safe configuration or areviewed database table. Do not expose provider credentials or template identifiers tothe planner/frontend.

Startup rules:

Fail startup when notifications and a channel are enabled but required structuralsettings are invalid.

Readiness must report notification worker/configuration health without exposingsecrets.

A temporarily unavailable provider should not make API liveness fail.

26. Worker Lifecycle and Deployment

The first processor may follow the existing in-process FastAPI lifespan worker pattern.Database row claiming keeps multiple application instances safe.

Production deployment should support running notification and channel dispatchers asseparate worker processes without changing domain interfaces.

Rules:

Start only when explicitly enabled.

Stop gracefully and release/cancel tasks on shutdown.

Expired leases make interrupted events claimable again.

Workers must not hold a database transaction while calling a provider.

Readiness distinguishes process liveness, database connectivity, notification workerhealth, channel worker health, and required template configuration.

27. Reconciliation

Add a periodic reconciliation query/job that detects:

eligible status-history/payment transitions without a notification event;

dispatched notification events without a delivery/outbound link;

delivery links without an outbound row;

stuck PROCESSING rows with expired leases; and

terminal provider failures requiring operator attention.

The primary transaction should prevent the first inconsistency. Reconciliation is asafety net for migration bugs, legacy data, and operational repair—not the normalevent-generation path.

Repairs must be idempotent and preserve the logical uniqueness key.

28. Security and Privacy

Scope every event, channel identity, order, template, and outbound lookup by trustedtenant.

Encrypt traffic and backups.

Use least-privilege database roles for workers.

Do not log full phone numbers, addresses, message bodies, content variables, orprovider credentials.

Do not use customer identifiers, order references, phone numbers, event IDs, ormessage bodies as metric labels.

Keep payloads minimal and versioned.

Retention/deletion policy must preserve legally required order/audit records whiledeleting notification content when permitted.

Never pass provider callback contents to the planner or conversation history.

Rate-limit public callback endpoints and validate provider signatures.

29. Observability

Expose low-cardinality metrics/events for:

notification events created by type;

notification claim/processing latency;

dispatched, suppressed, retryable, and dead-letter outcomes;

template locale fallback;

free-form versus approved-template mode;

channel outbound accepted/sent/delivered/read/failed;

expired leases recovered;

reconciliation discrepancies/repairs; and

worker health.

Use bounded notification_type, channel, status, and safe error category labels.Never label by tenant/customer/order/message ID.

Alerts should cover sustained dead letters, growing oldest-pending age, unavailablerequired templates, outbound failure spikes, and unhealthy workers.

30. Staff and Customer Interaction

Staff status transitions create events automatically through the fulfilmenttransaction; staff never manually send the standard notification.

Customer cancellation creates ORDER_CANCELLED automatically after the transactionsucceeds.

Customer status inquiries remain synchronous capabilities and do not create duplicateproactive notifications.

Retrying order confirmation/status transition with no new business transition doesnot create another event.

A notification failure never changes the authoritative status shown by customerorder-status capabilities.

31. Testing Strategy

31.1 Domain/service tests

Each eligible new order transition creates the correct notification event.

Repeated/no-op transition creates no new event.

COD confirmation never claims payment received.

Cancellation notification is created only after valid cancellation.

Invalid/skipped transition creates no event.

Payment events remain disabled until payment feature flag is enabled.

31.2 Transaction integration tests

Order status, history, inventory effects, and notification event commit together.

Forced outbox insertion failure rolls back the full transition.

Duplicate source transition cannot create duplicate logical notification.

Concurrent transition attempts create at most one event for the committed transition.

Tenant isolation is enforced.

31.3 Processor tests

Claiming uses leases and skip-locked behavior.

Processing creates one outbound row and one delivery link atomically.

Crash before atomic dispatch commit is safely retried.

Same event retry reuses the original outbound row.

Unsupported payload/template/channel is dead-lettered or suppressed as specified.

Transient failure backs off and retries.

Expired lease becomes claimable.

31.4 Template tests

Every enabled event/channel/locale has a valid reviewed template or configuredfallback.

Unknown and missing placeholders fail safely.

COD template does not say paid.

Exact order references, statuses, totals, currency, and payment method are preserved.

English, Hindi, Roman-script Hinglish, and tenant fallback outputs are tested.

Template rendering never invokes an LLM.

31.5 WhatsApp tests

Inside service window creates/sends free-form text mode.

Outside service window uses ContentSid with matching ContentVariables.

Template variables without Content SID are rejected before provider invocation.

Free-form sends omit content-template fields.

Duplicate callbacks do not regress delivery status.

Provider retryable, permanent, and ambiguous failures map correctly.

Missing approved template does not loop indefinitely.

31.6 End-to-end COD flow

Confirm a COD order.

Verify order/history/reservation/outbox commit atomically.

Run notification processor and verify one channel outbound record.

Run channel dispatcher with a mocked provider.

Record accepted, sent, and delivered callbacks.

Transition to PREPARING; verify exactly one new notification.

Transition to OUT_FOR_DELIVERY; verify exactly one new notification.

Transition to DELIVERED; verify inventory consumption and exactly one newnotification.

Repeat for customer cancellation, duplicate requests, worker crash, provider outage,closed WhatsApp service window, no supported channel, and cross-tenant isolation.

31.7 Reconciliation tests

Missing legacy event is detected and repaired once when eligible.

Dispatched-without-delivery inconsistency is repaired or surfaced safely.

Repeated reconciliation is idempotent.

Reconciliation never creates events for invalid/no-op transitions.

32. Acceptance Criteria

This milestone is complete when:

Every newly committed eligible order transition has one durable notification outboxevent in the same transaction.

A failed event insert rolls back the order/payment transition.

Repeated or concurrent transition attempts do not create duplicate logical events.

Notification processing creates one durable channel outbound delivery atomically.

Provider downtime does not block or roll back order fulfilment transactions.

Confirmation, preparing, out-for-delivery, delivered, and cancelled notificationsare supported for COD.

Payment notification contracts exist but cannot emit while production payments aredisabled.

WhatsApp sends free-form text inside the service window and an approved ContentTemplate outside it.

ContentVariables can never be sent without ContentSid.

Provider callbacks update delivery state without modifying order/payment state.

No supported channel is handled deterministically without infinite retry.

Proactive text is produced by reviewed versioned templates, never an LLM.

Customer language uses a bounded saved locale/style key with deterministic fallback.

Web-origin orders retain notification events even when proactive web delivery isunavailable.

Full PII and secrets are absent from payloads, routine logs, metrics, and prompts.

Health, metrics, alerts, dead letters, and reconciliation cover the completenotification pipeline.

Existing customer graph, capabilities, order lookup, REST, web, and WhatsApp inboundbehavior remains backward compatible.

Unit, transaction, processor, template, provider, concurrency, reconciliation, andend-to-end tests pass.

33. Deferred Work

Production Razorpay-backed payment notifications.

OTP and verified customer accounts.

Browser push, web notification center, WebSocket, or SSE delivery.

Email, SMS, mobile push, and Telegram providers.

Customer notification preference center.

Marketing campaigns and promotional consent.

Delivery ETA, driver assignment, and live tracking.

Human support escalation notifications.

Broker/CDC publishing when scale or cross-service fan-out requires it.


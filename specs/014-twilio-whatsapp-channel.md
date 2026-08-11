Twilio WhatsApp Channel Specification

1. Purpose

Add Twilio WhatsApp Sandbox as the first external conversational channel for the AICommerce Agent.

Customers who have joined the configured Twilio Sandbox must be able to send a textmessage through WhatsApp, continue a durable commerce conversation, and receive theapproved localized agent response through Twilio.

This milestone is sandbox-first and text-only. It must preserve the existing RESTchannel and keep all channel-specific behavior outside commerce capabilities and theLangGraph business workflow.

2. Frozen Architecture

The agent graph remains:

Planner -> Execute -> Response -> END

Twilio is a channel adapter around that graph:

WhatsApp user
    -> Twilio webhook
    -> TwilioWhatsAppChannelAdapter
    -> durable inbound inbox
    -> AgentRuntime.invoke
    -> Planner -> Execute -> Response
    -> durable outbound outbox
    -> Twilio Messages API
    -> WhatsApp user

Rules:

Do not add a Twilio or WhatsApp LangGraph node.

The webhook route is deterministic and must never call the LLM directly.

The planner never sees Twilio credentials, signatures, message SIDs, webhook fields,raw phone identifiers, or delivery-status payloads.

Capabilities remain channel-independent.

PostgreSQL is authoritative for inbound/outbound delivery records and channel-to-conversation mapping.

LangGraph checkpointing remains authoritative for short-term conversation state bythread_id/conversation_id.

Existing REST request and response behavior remains available for development anddiagnostics.

3. Twilio Sandbox Constraints

The implementation must document and test around these Sandbox characteristics:

The Sandbox is for testing and discovery, not production.

Only WhatsApp users who joined this Sandbox may exchange messages with it.

Sandbox membership expires and may require the user to rejoin.

Free-form replies are permitted only during the WhatsApp customer-service windowopened/refreshed by an inbound customer message.

Business-initiated messages outside that window require an approved template.

Custom production templates and sender onboarding are deferred.

The shared Sandbox sender and its rate limits are external constraints, not domainguarantees.

The agent's immediate reply to a new inbound message is inside the customer-servicewindow. Proactive notification delivery outside that window belongs to the laternotification/template milestone.

4. Scope

4.1 Included

Twilio Sandbox configuration through environment settings.

Signed inbound WhatsApp text webhook reception.

Durable inbound-message deduplication.

Trusted channel identity and stable conversation resolution.

Asynchronous invocation of the existing AgentRuntime.

Durable outbound message delivery through Twilio's Messages API.

Twilio message-status callback ingestion.

Ordered processing per conversation.

Retry and dead-letter behavior.

FastAPI lifespan workers with database row claiming.

Local HTTPS tunnel setup documentation.

Unit, integration, security, and concurrency tests.

4.2 Excluded

Production WhatsApp sender registration.

Direct Meta Cloud API integration.

Media download, upload, OCR, audio, location, contact, button, list, flow, catalog,reaction, and interactive-message support.

Custom approved message templates.

Proactive order notifications outside the customer-service window.

Marketing messages.

Human-agent inbox or handoff.

Group chat support.

Calling or voice-note transcription.

Treating the WhatsApp sender identifier as authenticated or verified identity.

5. Dependencies and Configuration

Add the supported Twilio Python SDK version to requirements.txt and pin it accordingto the project's dependency policy.

Required settings:

TWILIO_WHATSAPP_ENABLED=true
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
TWILIO_WHATSAPP_PUBLIC_BASE_URL=https://example-tunnel-or-domain
TWILIO_WHATSAPP_INBOUND_PATH=/webhooks/twilio/whatsapp
TWILIO_WHATSAPP_STATUS_PATH=/webhooks/twilio/whatsapp/status
TWILIO_WHATSAPP_PROCESSOR_ENABLED=true
TWILIO_WHATSAPP_PROCESSOR_INTERVAL_SECONDS=1
TWILIO_WHATSAPP_PROCESSOR_BATCH_SIZE=20
TWILIO_WHATSAPP_MAX_ATTEMPTS=5
TWILIO_WHATSAPP_LEASE_SECONDS=120

Rules:

Fail startup when Twilio is enabled and required settings are absent or malformed.

Require HTTPS for the configured public base URL except in isolated automated tests.

Normalize the public base URL by removing a trailing slash.

Build exact webhook URLs from the configured public base URL and fixed paths.

Do not use arbitrary request Host or untrusted forwarded headers to construct theURL passed into Twilio signature validation.

Never print Account SID, Auth Token, signature, full sender number, or configuredcallback URLs containing secrets.

Settings come from .env/environment-backed BaseSettings, never planner prompts.

6. HTTP Endpoints

6.1 Inbound message webhook

POST /webhooks/twilio/whatsapp
Content-Type: application/x-www-form-urlencoded

The route must:

read form data without converting it into an LLM input yet;

reconstruct the exact configured public webhook URL;

validate X-Twilio-Signature with Twilio's RequestValidator and Auth Token;

reject invalid signatures before any durable business effect;

validate required fields and supported channel format;

insert/deduplicate the inbound message by Twilio MessageSid;

update the trusted channel's last-inbound timestamp;

return an empty successful TwiML response immediately; and

leave agent execution to the background processor.

Successful response:

<?xml version="1.0" encoding="UTF-8"?>
<Response></Response>

Do not wait for Gemini, LangGraph, commerce SQL, or the Twilio outbound API beforeacknowledging a valid inbound webhook.

6.2 Status callback

POST /webhooks/twilio/whatsapp/status
Content-Type: application/x-www-form-urlencoded

The status route must validate the Twilio signature using its own exact configured URL,then persist/deduplicate the status transition. Expected statuses include:

queued -> sent -> delivered -> read
                  \-> failed

Do not send status callbacks to the planner or conversation history.

6.3 Health behavior

Application health must distinguish:

route/process is running;

database workers are healthy; and

Twilio credentials/configuration are syntactically present.

Health checks must not send a WhatsApp message or expose credentials.

7. Inbound Webhook Contract

Required Twilio fields:

Field

Use

MessageSid

Provider idempotency key

AccountSid

Must equal configured account

From

Trusted transport sender after signature validation

To

Must equal configured Sandbox sender

Body

Customer text for supported text messages

NumMedia

Detect unsupported media

WaId

Optional normalized WhatsApp identifier; do not trust over signed request scope

ProfileName

Optional display metadata only; never trusted customer name

Validation rules:

Require a valid Twilio message SID shape and bounded field sizes.

Require From and To to use the whatsapp: scheme.

Compare AccountSid and To with configured values.

Normalize the sender into an E.164-based channel identifier after signaturevalidation.

Preserve Unicode text exactly apart from established safe whitespace normalization.

Enforce a configured maximum inbound body size before invoking the agent.

Treat an empty body with media as unsupported media, not as a greeting.

Never use ProfileName as checkout name, saved profile identity, consent, orauthentication evidence.

8. Trusted Channel Identity and Conversation Resolution

Create trusted runtime context outside LLM arguments:

CustomerChannelContext(
    tenant_id=configured_tenant_id,
    conversation_id=resolved_conversation_id,
    channel=ChannelName.TWILIO_WHATSAPP,
    channel_customer_id=normalized_sender,
)

The Twilio sender ID is a stable transport identifier for this channel. It is not averified legal identity or proof that delivery details belong to the person.

Persist channel conversation mapping:

class ChannelConversation(BaseModel):
    id: UUID
    tenant_id: UUID
    channel: ChannelName
    channel_customer_id: str
    conversation_id: UUID
    last_inbound_at: datetime
    created_at: datetime
    updated_at: datetime

Required uniqueness:

UNIQUE (tenant_id, channel, channel_customer_id)
UNIQUE (tenant_id, conversation_id)

The first valid inbound message creates the mapping and a new conversation UUID.Subsequent messages reuse it so LangGraph restores the same thread.

Do not derive conversation IDs inside prompts. Do not use a phone number as theLangGraph thread ID directly. Do not allow a Twilio form field to override tenant ID orconversation ID.

Saved delivery profiles may use this trusted channel identity under the existing saved-details consent rules. The transport identifier still must not be described as verified.

9. Persistence Model

Create application tables through Alembic.

9.1 channel_conversations

Column

Type

Rule

id

UUID

Primary key

tenant_id

UUID

Required

channel

text

Required

channel_customer_id

text

Required sensitive identifier

conversation_id

UUID

Required

last_inbound_at

timestamptz

Required

created_at

timestamptz

Required

updated_at

timestamptz

Required

9.2 channel_inbound_messages

Column

Type

Rule

id

UUID

Primary key

tenant_id

UUID

Required

channel

text

Required

provider_message_id

text

Required

conversation_id

UUID

Required

sender_id

text

Required sensitive identifier

recipient_id

text

Required

body

text

Required or empty for unsupported type

message_kind

text

TEXT or UNSUPPORTED in this milestone

status

text

Processing state

attempt_count

integer

Required, starts at zero

next_attempt_at

timestamptz

Required

lease_expires_at

timestamptz

Nullable

last_error_code

text

Nullable bounded category

received_at

timestamptz

Required

processed_at

timestamptz

Nullable

Required constraint:

UNIQUE (channel, provider_message_id)
INDEX (status, next_attempt_at, received_at)
INDEX (tenant_id, conversation_id, received_at)

9.3 channel_outbound_messages

Column

Type

Rule

id

UUID

Primary key and local idempotency key

tenant_id

UUID

Required

channel

text

Required

conversation_id

UUID

Required

source_inbound_id

UUID

Required unique foreign key

recipient_id

text

Required sensitive identifier

sender_id

text

Required configured sender

body

text

Required approved agent response

provider_message_id

text

Nullable until accepted by Twilio

status

text

Delivery/processing state

attempt_count

integer

Required

next_attempt_at

timestamptz

Required

lease_expires_at

timestamptz

Nullable

last_error_code

text

Nullable bounded category

created_at

timestamptz

Required

sent_at

timestamptz

Nullable

updated_at

timestamptz

Required

Required constraints:

UNIQUE (source_inbound_id)
UNIQUE (channel, provider_message_id)
INDEX (status, next_attempt_at, created_at)

9.4 channel_delivery_events

Persist status events with unique (channel, provider_message_id, status) so duplicateTwilio callbacks are harmless. Retain bounded error code/category, not unrestrictedprovider error text containing customer data.

10. Processing States

Inbound states:

RECEIVED -> PROCESSING -> PROCESSED
              |             |
              v             v
           RETRYABLE     (outbound queued)
              |
              v
         DEAD_LETTER

Outbound states:

PENDING -> SENDING -> ACCEPTED -> SENT -> DELIVERED -> READ
              |          |
              v          v
           RETRYABLE   FAILED
              |
              v
         DEAD_LETTER

Only legal monotonic transitions may apply. Repeated or older callbacks are recordedidempotently without moving state backwards. FAILED and READ are terminal for thismilestone, except operational manual replay from dead letter.

11. Inbound Processor

Run a configurable periodic worker from FastAPI lifespan using the existing in-processjob pattern.

Each cycle must:

claim a bounded batch using a short transaction and FOR UPDATE SKIP LOCKED or anequivalent lease;

process messages in received_at, id order;

ensure only one message for a conversation is processed at a time;

release the database transaction before calling the agent;

invoke AgentRuntime with trusted channel context and inbound request idempotency;

persist the generated reply and mark inbound processed in one transaction; and

let the outbound dispatcher deliver the persisted reply separately.

Agent invocation request identity:

twilio-whatsapp:{MessageSid}

Side-effecting capability execution must reuse the existing application idempotencyboundary so replaying one Twilio message cannot add cart items or confirm an ordertwice.

11.1 Conversation ordering

Two messages from one WhatsApp user may arrive close together. The processor must notrun the same LangGraph thread concurrently.

Use a tenant/conversation-scoped advisory lock, lease, or claim rule. A later messagewaits until the earlier message is PROCESSED or terminal. Messages from differentconversations may run concurrently within configured limits.

11.2 Persist-before-send rule

Once the agent returns, persist the exact customer-facing reply before calling Twilio.

If Twilio sending fails, retry the persisted outbound message. Never rerun the planneror capability merely to regenerate the same outbound reply.

12. Unsupported Messages

For NumMedia > 0, empty text, or another unsupported message type:

do not download media;

do not send media URLs to the LLM;

create a deterministic approved response explaining that text messages are supportedcurrently;

enqueue that response through the same outbound outbox; and

mark the inbound message processed.

If a message contains both text and media, the milestone policy is to ignore the mediaand process text only if the text is non-empty, while including no media-derived facts.

13. Outbound Twilio Adapter

Define a channel-neutral boundary:

class OutboundMessageProvider(Protocol):
    async def send_text(
        self,
        recipient_id: str,
        body: str,
        idempotency_key: UUID,
        status_callback_url: str,
    ) -> ProviderMessageResult: ...

TwilioWhatsAppMessageProvider must call Twilio's Messages resource with:

from_ = configured TWILIO_WHATSAPP_FROM
to = trusted recipient_id
body = persisted approved reply
status_callback = exact configured status URL

Twilio does not provide a universal server-side idempotency guarantee for blindlyrepeated message-creation calls. Therefore:

persist local send intent before the API call;

lease one outbound row to one worker;

store returned Twilio Message SID immediately;

never retry after an accepted SID is stored;

treat network timeout after an ambiguous send as an operational state requiringreconciliation/manual inspection rather than automatically producing duplicates; and

never regenerate the reply during send retry.

Validate response body length using the provider adapter's configured limits. Do notsilently truncate product lists, prices, quantities, addresses, order status, or paymentmeaning. Return a safe operational failure if an approved reply cannot be delivered asone supported text message in this milestone.

14. Webhook Signature Security

Use Twilio's official RequestValidator.

For form-encoded webhooks, validation input must include:

the exact externally configured request URL;

all received form parameters as required by the Twilio SDK; and

X-Twilio-Signature.

Security rules:

Missing or invalid signature returns 403 and writes no inbox/status event.

Validate before trusting AccountSid, From, To, MessageSid, or any body text.

Do not disable validation for local tunnels.

Use separate explicit test fixtures to generate valid signatures in automated tests.

Do not log the Auth Token or signature.

Rotate the Auth Token/configuration through deployment secrets, not source changes.

Configure trusted proxy behavior deliberately; do not reconstruct public URLs fromarbitrary forwarded headers.

15. Retry and Dead-Letter Policy

Retry only temporary failures such as:

transient database connectivity after safe rollback;

temporary LLM/provider unavailability before a durable response exists;

Twilio 5xx, throttling, or documented retryable response before acceptance; and

recoverable worker interruption with an expired lease.

Do not retry indefinitely:

invalid webhook signature;

malformed/oversized input;

unsupported recipient/Sandbox membership;

permanent Twilio authentication/configuration error;

content rejected as permanently invalid; or

completed inbound/outbound records.

Use bounded exponential backoff with jitter and configured maximum attempts. Afterexhaustion, set DEAD_LETTER, emit an operational alert/metric, and preserve enoughnon-sensitive identifiers for investigation.

16. Status Callback Processing

Map Twilio statuses into internal delivery states without involving the LLM:

Twilio status

Internal status

queued

ACCEPTED

sent

SENT

delivered

DELIVERED

read

READ

failed/undelivered

FAILED

Rules:

Resolve only a known outbound provider message SID.

Verify account and sender/recipient context when supplied.

Store each distinct transition idempotently.

Never move a message from READ/DELIVERED back to SENT/ACCEPTED.

Store bounded Twilio error codes, not unrestricted error content.

Unknown SIDs are quarantined or logged safely; they never create customer/order data.

17. Customer-Service Window

Update channel_conversations.last_inbound_at for every valid supported inboundcustomer message.

For this milestone:

immediate agent replies are eligible free-form responses;

outbound delivery must verify it is still within the configured 24-hour window;

if processing was delayed beyond the window, do not attempt an unapproved free-formmessage;

mark the outbound row with TEMPLATE_REQUIRED or an equivalent non-retryable state;and

do not invent or use a template.

Future proactive notifications must use approved Twilio Content Templates outside thewindow. Sandbox custom-template support is not part of this milestone.

18. Response Localization

The existing Response Node remains the only generator of normal agent replies.

Match the latest inbound customer's language, script, tone, and chat style.

Preserve approved product names, prices, quantities, units, ordinals, order/paymentreferences, and delivery details exactly as required by current response rules.

Do not prepend channel-specific greetings or signatures to every message.

Preserve newlines in the Twilio body.

Do not expose internal Twilio, webhook, processing, or retry terminology.

Unsupported-message replies are deterministic and localized through approved responsemeaning or the existing response renderer; they do not use media content.

19. Privacy and Data Handling

Treat From, To, WaId, ProfileName, message body, and delivery details assensitive/customer data.

Do not print raw webhook payloads in normal logs.

Do not put full sender numbers in metrics, trace attributes, error messages, orplanner prompts.

Use internal UUIDs or a keyed/non-reversible identifier for correlation logs.

Do not persist Twilio Auth Token or request signatures.

Define retention/deletion rules for channel message bodies before production.

Saved delivery data continues to require explicit consent.

The WhatsApp transport sender must never be described as phone-verified identity.

20. Application Wiring

Suggested placement, adapted to the current repository:

app/api/twilio_whatsapp_webhooks.py
app/jobs/channel_inbound_processor.py
app/jobs/channel_outbound_dispatcher.py
channels/models.py
channels/repositories.py
channels/services/inbound_message_service.py
channels/services/outbound_message_service.py
channels/services/channel_conversation_service.py
infrastructure/channels/twilio/request_validator.py
infrastructure/channels/twilio/message_provider.py
infrastructure/database/repositories/postgres_channel_repository.py
alembic/versions/
tests/unit/
tests/integration/

If the repository already has a channel/application boundary, use it rather thancreating a parallel abstraction. Keep Twilio SDK types in infrastructure and HTTProutes, not commerce domain models.

FastAPI lifespan must:

initialize the Twilio client/provider when enabled;

start inbound and outbound periodic tasks when configured;

keep task failures isolated so one cycle does not permanently stop the worker;

signal cancellation during shutdown; and

await clean worker termination before closing shared resources.

21. Local Sandbox Setup

Document these developer steps without storing secrets in the repository:

Activate the Twilio Sandbox for WhatsApp.

Send the displayed join <sandbox-code> message from the test WhatsApp account.

Start PostgreSQL and FastAPI locally.

Start an HTTPS development tunnel to FastAPI.

Set TWILIO_WHATSAPP_PUBLIC_BASE_URL to the exact public tunnel origin.

Configure the Twilio Sandbox When a Message Comes in URL to:

{PUBLIC_BASE_URL}/webhooks/twilio/whatsapp

Configure method POST.

Configure the Sandbox status callback URL to the exact status path.

Restart the application after environment changes.

Send Hi and verify inbound, agent processing, outbound acceptance, and statusprogression.

When the tunnel URL changes, update both environment configuration and Twilio Sandboxconfiguration before testing signatures.

22. Observability

Emit structured metrics for:

valid/invalid inbound webhooks;

duplicate inbound messages;

inbox processing latency and failures;

agent invocation latency by safe category;

outbound pending/accepted/delivered/read/failed counts;

worker retry and dead-letter counts;

conversation-ordering delays; and

signature/configuration failures without secret data.

Use correlation fields such as internal inbound UUID, outbound UUID, and conversationUUID. Do not use full customer phone identifiers as metric labels.

23. Testing Requirements

23.1 Signature and route tests

Correctly signed form webhook is accepted.

Missing/invalid signature is rejected with no database write.

Signature validation uses the configured exact public URL.

A changed public URL causes validation failure until Twilio configuration matches.

Wrong Account SID, recipient, scheme, or malformed message is rejected safely.

Duplicate MessageSid returns success and creates one inbox row.

Valid route returns empty TwiML without invoking the agent synchronously.

23.2 Identity and conversation tests

First sender message creates one channel conversation.

Repeated sender messages reuse the same conversation/thread ID.

Same sender under two tenants cannot cross data.

REST and Twilio conversations remain distinct channel namespaces.

Sender/ProfileName is never treated as checkout name or verified identity.

23.3 Processor tests

Inbox processing invokes the runtime once with exact text and trusted context.

Reprocessing the same inbound ID does not repeat a side-effecting capability.

Two messages in one conversation execute in order and never concurrently.

Different conversations may process concurrently.

Agent reply is persisted before outbound delivery.

Outbound failure retries persisted text without reinvoking the agent.

Lease expiry safely recovers interrupted work.

Retry exhaustion reaches dead letter.

23.4 Twilio provider and callback tests

Outbound call uses configured sender, trusted recipient, body, and callback URL.

Returned provider message SID is persisted once.

Duplicate status callbacks are idempotent.

Status transitions cannot move backwards.

Failed status stores bounded error category.

Ambiguous send timeout does not automatically duplicate the message.

23.5 Conversation and commerce integration tests

Hi returns a localized greeting through WhatsApp.

Product search, selection, quantity, cart, checkout, and COD confirmation completethrough one restored WhatsApp conversation.

Hinglish/Hindi messages receive matching language/style responses.

Duplicate inbound add-to-cart/confirm-order webhooks do not duplicate business data.

Saved delivery profile uses trusted Twilio channel identity only with explicit consent.

Online payment link/status meaning remains grounded and does not expose secrets.

Unsupported media receives one deterministic text-only response.

23.6 Lifespan tests

Workers start only when enabled.

Tests can disable workers deterministically.

One cycle failure does not kill future cycles.

Shutdown cancels and awaits tasks before closing database/provider resources.

24. Definition of Done

This milestone is complete when:

a joined Sandbox user can send text and receive the agent reply end to end;

every webhook is signature-validated before trusted use;

duplicate Twilio deliveries cannot duplicate agent/business effects;

trusted tenant/channel/customer/conversation context stays outside LLM arguments;

messages from one conversation process in order;

webhook acknowledgement does not wait for LLM execution;

agent replies are persisted before Twilio sending;

outbound retries never rerun the planner or commerce capability;

delivery callbacks are verified, idempotent, and monotonic;

unsupported media is handled safely without download or LLM exposure;

REST remains functional;

Sandbox limitations and 24-hour window are enforced;

secrets and customer identifiers are excluded from prompts and routine logs;

all migrations and required tests pass; and

the graph remains Planner -> Execute -> Response -> END.

25. Deferred Next Milestones

Reliable customer notifications using transactional outbox and Twilio templates.

Media/image/audio support with explicit security and privacy controls.

Human-agent handoff and staff inbox.

OTP-based customer authentication when required.

Production WhatsApp sender onboarding and approved templates.

Production security hardening, observability, rate limiting, deployment, backup, anddisaster recovery.
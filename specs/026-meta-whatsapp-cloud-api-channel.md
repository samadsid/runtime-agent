Meta WhatsApp Cloud API Channel Specification

1. Purpose

Integrate the AI Commerce Agent directly with Meta WhatsApp Cloud API using theconfigured Meta test phone number and Phone Number ID.

Customers must be able to send WhatsApp text messages, continue a durable commerceconversation, and receive the approved localized agent response through Meta while theexisting runtime remains unchanged:

WhatsApp customer
    -> Meta webhook
    -> durable inbound inbox
    -> existing inbound channel worker
    -> CommerceRuntime
    -> Planner -> Execute -> Response
    -> durable outbound outbox
    -> existing outbound dispatcher
    -> Meta Graph API
    -> WhatsApp customer

This milestone adds Meta as a selectable WhatsApp transport alongside Twilio. Exactlyone WhatsApp provider is selected at startup through a provider-neutral compositionboundary. Changing provider does not replace the PostgreSQL inbox/outbox, conversationmapping, runtime request idempotency, customer profile memory, commerce graph, ornotification outbox.

2. Prerequisites

Meta app with the WhatsApp use case enabled.

Meta test WhatsApp Business Account (WABA).

Claimed Meta test phone number.

Phone Number ID.

WABA ID.

Temporary access token for development testing.

Meta App Secret.

A verified test-recipient WhatsApp number.

Public HTTPS URL for webhook configuration.

Existing channel inbox/outbox tables and workers from specification 014.

Customer order notification pipeline from specification 019.

PostgreSQL and Alembic migrations.

Existing health, metrics, retry, leasing, and runtime idempotency boundaries.

3. Goals

Receive signed Meta WhatsApp webhook events safely.

Verify Meta's webhook subscription challenge.

Deduplicate incoming customer messages by Meta message ID (wamid).

Resolve a stable tenant/channel customer to the existing conversation UUID.

Acknowledge valid webhooks before running the LLM or commerce workflow.

Reuse the existing inbound processor and outbound dispatcher.

Send free-form text responses through the Meta Graph API.

Support approved template messages when the customer-service window requires them.

Record provider acceptance and sent, delivered, read, and failed states.

Prevent webhook replay from duplicating cart, checkout, order, or profile effects.

Keep Meta credentials and payload details outside prompts and commerce capabilities.

Preserve REST/web channels.

Select twilio, meta_cloud, or disabled through one validated setting.

Keep provider selection in application composition rather than scattering switchstatements through routes, workers, repositories, or commerce code.

Allow Twilio code to remain available but unselected during Meta acceptance.

4. Non-goals

Production business verification or production phone-number onboarding.

Creating or approving Meta message templates automatically.

Marketing messages, campaigns, broadcasts, or audience management.

Media download/upload, images, documents, audio, stickers, location, contacts,reactions, buttons, lists, flows, commerce catalog messages, or calls.

Voice-note transcription.

Group conversations.

Human-agent inbox, assignment, or handoff.

Customer OTP or proof that the WhatsApp sender owns delivery details.

Automatically merging existing provider-specific conversation/profile records withoutan explicit, validated migration policy.

Exactly-once delivery by an external provider.

Calling Meta synchronously from a commerce transaction.

Adding a WhatsApp-specific LangGraph node.

5. Frozen Architecture

The commerce graph remains:

Planner -> Execute -> Response -> END

The channel architecture remains:

Meta POST webhook
    -> authenticate raw body
    -> validate and normalize supported events
    -> insert/deduplicate inbox or delivery event
    -> return HTTP 200

Inbound worker
    -> claim inbox row
    -> conversation lock
    -> invoke CommerceRuntime with trusted context
    -> persist generated reply as outbound row

Outbound worker
    -> claim outbound row
    -> enforce service-window/template policy
    -> MetaWhatsAppMessageProvider
    -> persist provider wamid or safe failure state

Meta status webhook
    -> authenticate and normalize status
    -> persist idempotently and monotonically

Rules:

Webhook routes never invoke Gemini, LangGraph, or commerce services directly.

The planner never receives access tokens, app secrets, verification tokens, WABA IDs,Phone Number IDs, webhook signatures, raw payloads, or provider errors.

Capabilities remain channel-independent.

PostgreSQL is authoritative for channel mappings, inbox/outbox processing, deliveryevents, leases, attempts, and dead-letter state.

LangGraph checkpointing remains authoritative for short-term conversation state byconversation/thread ID.

Business-side effects use the existing trusted request ID derived from the inboundprovider message ID.

Order/customer notification transactions insert channel-neutral notification intent;they never call Meta.

6. WhatsApp Provider Selection

Separate the customer-facing channel from its delivery provider:

class ChannelName(str, Enum):
    REST = "rest"
    WEB = "web"
    WHATSAPP = "whatsapp"


class WhatsAppProviderName(str, Enum):
    TWILIO = "twilio"
    META_CLOUD = "meta_cloud"

Configuration selects exactly one active WhatsApp provider:

WHATSAPP_PROVIDER=disabled | twilio | meta_cloud

Use a composition-root factory or registry:

def build_whatsapp_channel(settings: Settings) -> WhatsAppChannelComponents | None:
    match settings.WHATSAPP_PROVIDER:
        case "disabled":
            return None
        case "twilio":
            return build_twilio_whatsapp_components(settings)
        case "meta_cloud":
            return build_meta_whatsapp_components(settings)
        case _:
            raise ValueError("Unsupported WhatsApp provider")

The switch belongs only in application composition. After startup, workers depend oninterfaces such as:

InboundWebhookAdapter
OutboundMessageProvider
DeliveryStatusNormalizer
WhatsAppPolicy

They do not repeatedly inspect configuration or branch on provider names.

Provider-selection rules:

disabled starts no WhatsApp provider or WhatsApp worker.

twilio validates only required Twilio settings and selects the Twilio adapter.

meta_cloud validates only required Meta settings and selects the Meta adapter.

Invalid or unsupported values fail startup.

Do not use separate enabled booleans that allow both providers to become activeaccidentally.

Provider-specific webhook routes may remain registered, but an unselected provider'sroute returns 404 and performs no writes.

Health/readiness identifies the selected provider with a safe enum only.

Switching provider is an operator deployment action, never an LLM/planner decision.

Pending outbound rows retain their persisted provider. Before switching, drain orexplicitly disposition pending/retryable/ambiguous rows for the old provider.

6.1 Provider-neutral identity

New records use:

channel = whatsapp
provider = twilio | meta_cloud

Provider message identity is scoped by provider:

UNIQUE (provider, provider_message_id)

Conversation identity is channel-level:

UNIQUE (tenant_id, channel, channel_customer_id)

This allows an intentionally migrated WhatsApp customer to retain one conversationwhen the business changes transport provider. It must not silently merge conflictinghistorical mappings.

6.2 Migration from existing Twilio data

Add a provider column before normalizing channel values.

Backfill existing twilio_whatsapp rows with provider=twilio.

Normalize their channel to whatsapp only after checking uniqueness collisions.

Preserve provider IDs, statuses, bodies, timestamps, and audit history.

Do not infer Meta rows from Twilio rows.

Do not merge profiles merely from an untrusted typed phone number.

Do not delete Twilio records or dependencies in this milestone.

Only one provider should actively own WhatsApp outbound delivery for a tenant duringnormal operation.

7. Configuration

Load configuration through BaseSettings and environment variables:

WHATSAPP_PROVIDER=meta_cloud
META_GRAPH_API_VERSION=
META_WHATSAPP_PHONE_NUMBER_ID=
META_WHATSAPP_BUSINESS_ACCOUNT_ID=
META_WHATSAPP_ACCESS_TOKEN=
META_WHATSAPP_APP_SECRET=
META_WHATSAPP_VERIFY_TOKEN=
META_WHATSAPP_PUBLIC_BASE_URL=
META_WHATSAPP_WEBHOOK_PATH=/webhooks/meta/whatsapp
WHATSAPP_PROCESSOR_ENABLED=true
WHATSAPP_PROCESSOR_INTERVAL_SECONDS=1
WHATSAPP_PROCESSOR_BATCH_SIZE=20
WHATSAPP_MAX_ATTEMPTS=5
WHATSAPP_LEASE_SECONDS=120
WHATSAPP_CUSTOMER_SERVICE_WINDOW_HOURS=24
META_WHATSAPP_HTTP_TIMEOUT_SECONDS=15
META_WHATSAPP_MAX_INBOUND_BODY_BYTES=65536
META_WHATSAPP_MAX_TEXT_CHARS=4096

Rules:

Pin a supported Graph API version explicitly; do not use an unversioned Graph URL.

Select the version shown/supported in the Meta app at implementation time and recordits retirement review date in operational documentation.

Fail startup when WHATSAPP_PROVIDER=meta_cloud and required Meta values are absentor malformed.

When WHATSAPP_PROVIDER=twilio, validate Twilio settings without requiring Metacredentials.

When WHATSAPP_PROVIDER=disabled, require neither provider's credentials.

Shared worker/window settings apply to the selected provider; provider credentials,webhook validation, HTTP limits, and sender-resource settings remain provider-specific.

Require an HTTPS public base URL outside isolated automated tests.

Phone Number ID and WABA ID are identifiers, not phone numbers; validate bounded digitstrings without converting them to integers.

The verification token is a high-entropy secret created by the operator.

The App Secret validates webhook authenticity.

The access token authorizes Graph API calls.

Never expose any of these secrets to the mobile app, frontend, prompts, logs, metrics,health responses, or API documentation examples.

Temporary development tokens expire. Production readiness requires a properly scoped,rotated, long-lived system-user token stored through approved secret management.

.env and secret files remain outside source control.

Generate a development verification token with a secure tool, for example:

openssl rand -hex 32

8. Meta Setup Requirements

Before end-to-end testing:

Add and verify the intended recipient number in Meta's test-recipient list.

Confirm Meta's dashboard-generated hello_world template reaches that recipient.

Confirm a direct Graph API request returns a provider wamid.

Expose the backend webhook through a public HTTPS URL.

Configure callback URL:

{META_WHATSAPP_PUBLIC_BASE_URL}/webhooks/meta/whatsapp

Enter the exact configured verification token in Meta.

Subscribe the app/WABA to the WhatsApp messages webhook field.

Send a customer message to the Meta test number and verify the POST reaches thebackend.

Do not paste access tokens or App Secrets into tickets, chat messages, screenshots, orterminal output captured for support.

9. HTTP Endpoints

Use one path with separate methods:

GET  /webhooks/meta/whatsapp
POST /webhooks/meta/whatsapp

Do not require application JWT authentication on these endpoints. Their authenticationboundaries are Meta verification token (GET) and Meta request signature (POST).

9.1 Verification endpoint

Meta sends query parameters conceptually named:

hub.mode
hub.verify_token
hub.challenge

The route must:

require hub.mode to equal subscribe;

require bounded non-empty token and challenge values;

compare the received token with configured verification token using a timing-safecomparison;

return the raw challenge as text/plain with HTTP 200 on success;

return HTTP 403 on token/mode mismatch; and

avoid logging token or challenge contents.

Verification performs no database write and no external Graph request.

9.2 Event endpoint

The POST route must:

reject unsupported content type and oversized bodies;

read the exact raw request bytes once;

validate X-Hub-Signature-256 before trusting or parsing business fields;

parse bounded JSON after signature success;

validate top-level object and supported event shapes;

validate configured WABA and Phone Number ID ownership where supplied;

normalize every supported message/status event independently;

persist/deduplicate accepted events with one bounded database transaction per batchor another failure-safe strategy;

return HTTP 200 promptly; and

leave runtime and outbound processing to workers.

Do not return generated chat content in the webhook response.

10. POST Signature Validation

Require header format:

X-Hub-Signature-256: sha256=<lowercase-or-valid-hex-digest>

Calculate:

expected = hmac.new(
    app_secret.encode("utf-8"),
    raw_request_body,
    hashlib.sha256,
).hexdigest()

Then compare the received and expected digest with hmac.compare_digest.

Rules:

Sign the raw bytes, never parsed/re-serialized JSON.

Reject missing, malformed, incorrect, or duplicate ambiguous signature headers.

Verify before creating channel mappings, inbox rows, delivery events, logs containingpayload fields, or metrics labeled from payload values.

Invalid signature returns HTTP 403 and produces only a low-cardinality securitymetric/log event.

Never log the received signature, calculated digest, App Secret, or raw body.

A reverse proxy must pass the original body unchanged.

11. Webhook Envelope Validation

Supported events are expected under the WhatsApp Business Account envelope containingentries and changes for the messages field.

Validation rules:

Top-level object must identify the WhatsApp Business Account webhook family.

Each entry ID, when present, must equal the configured WABA ID.

Each relevant change must use the expected messages field.

metadata.phone_number_id, when present, must equal the configured Phone Number ID.

Arrays and strings are bounded before iteration/storage.

Unknown top-level/change fields are ignored safely after signature validation.

A supported batch may contain inbound messages, statuses, or both.

One malformed event must not cause trusted valid siblings to be processed twice.

Decide and test atomic batch behavior: either all normalized database inserts committogether or each event has independent durable identity and safe retry. The chosenbehavior must not acknowledge unpersisted valid events silently.

Unsupported but correctly signed events may be acknowledged and counted without beingsent to the planner.

12. Inbound Message Contract

Support text messages initially.

Relevant normalized values:

Meta value

Internal use

message id

Provider idempotency key (wamid)

message from

Trusted transport sender after signature validation

message timestamp

Provider event time, bounded/validated

message type

TEXT or UNSUPPORTED mapping

text body

Customer message text

metadata phone_number_id

Must match configured sender resource

contacts profile name

Optional untrusted display metadata only

Rules:

Require a non-empty bounded provider message ID with the expected safe prefix/shapepolicy; do not assume a fixed total length that Meta may change.

Normalize from as an international phone identifier after validating digits andlength; store a canonical internal E.164 representation such as +919....

Convert to Meta's digits-only to representation only at the outbound adapter.

Preserve Unicode message content apart from established safe whitespacenormalization.

Enforce maximum UTF-8 body bytes and maximum configured customer-facing text length.

Empty text is unsupported, not a greeting.

Profile name is not a checkout name, saved customer name, consent, legal identity, orauthentication evidence.

context/reply metadata may be retained only as bounded diagnostic linkage if needed;it does not override conversation identity.

Inbound timestamps do not control trusted server transaction time.

13. Unsupported Messages

Map non-text types to MessageKind.UNSUPPORTED after signature validation and durablededuplication.

Examples:

image
audio
video
document
sticker
location
contacts
reaction
interactive
button
order
system
unknown future type

The inbound worker returns one deterministic localized text-only limitation response.Do not send media identifiers, URLs, captions, or binary content to the planner in thismilestone. Do not download media.

Duplicate unsupported messages must not produce duplicate replies.

14. Trusted Channel Identity and Conversation Resolution

Build trusted context outside LLM arguments:

CustomerChannelContext(
    tenant_id=configured_tenant_id,
    conversation_id=resolved_conversation_id,
    channel=ChannelName.WHATSAPP,
    channel_customer_id=canonical_sender,
    request_id=f"meta-whatsapp:{provider_message_id}",
)

Persist/reuse mapping through the existing channel conversation table:

UNIQUE (tenant_id, channel, channel_customer_id)
UNIQUE (tenant_id, conversation_id)

Rules:

First valid WhatsApp inbound creates a mapping/conversation when no intentionallymigrated mapping exists.

Subsequent Meta messages from the same canonical sender reuse it.

Do not use the phone number directly as LangGraph thread ID.

Do not let payload fields override tenant or conversation UUID.

Do not attach the sender to an unrelated REST profile solely by phone match.

A provider switch may reuse an intentionally normalized WhatsApp mapping; it must notperform an implicit runtime merge of conflicting historical mappings.

Saved profile lookup may use this trusted channel identity under the existing profilerules, but the UI/agent must not claim OTP-verified ownership.

15. Persistence

Reuse existing tables where their schemas are provider-neutral:

channel_conversations
channel_inbound_messages
channel_outbound_messages
channel_delivery_events

Required channel/provider values:

channel = whatsapp
provider = meta_cloud

15.1 Inbound uniqueness

Enforce:

UNIQUE (provider, provider_message_id)

Include tenant in the unique key if the existing multi-tenant provider identity policyrequires it, but never permit the same Meta wamid to execute twice within its trustedprovider scope.

15.2 Outbound message shape

Extend outbound records only where required to distinguish:

TEXT
TEMPLATE

Suggested provider-neutral fields:

Field

Purpose

provider

Provider selected and persisted when the outbound row is created

message_kind

TEXT or TEMPLATE

body

Rendered text for free-form messages; safe preview for template if applicable

template_key

Internal reviewed template identifier, nullable

template_name

Configured Meta-approved template name, nullable

template_language

Configured language code, nullable

template_parameters

Versioned approved structured values, nullable JSONB

provider_message_id

Meta wamid, nullable until accepted

Do not store access tokens, App Secrets, signatures, unrestricted webhook bodies, orunreviewed template payloads.

15.3 Delivery-event uniqueness

Store provider message ID, normalized state, provider event timestamp, bounded errorcode/category, and received time. Enforce a durable uniqueness key that makes duplicateMeta status deliveries harmless, for example:

(provider, provider_message_id, normalized_status, provider_event_timestamp,
 bounded_error_code)

Do not use unrestricted error text in an index.

15.4 Migration

Alembic migration must:

add provider values twilio and meta_cloud;

add provider columns to provider-message and delivery records;

normalize the customer-facing channel to whatsapp after collision checks;

add provider-neutral message/template fields only when absent;

backfill Twilio rows without changing their provider message identity or content;

preserve all REST rows;

add provider-scoped indexes/constraints without rewriting customer identifiers;

document downgrade behavior so Meta rows are not silently deleted or mislabeled.

16. Inbound Worker Integration

Reuse ChannelInboundProcessor with channel/provider-neutral dependencies.

For each claimed inbound row:

acquire tenant/conversation advisory or repository lock;

skip safely if already completed;

produce deterministic response for unsupported type, or construct conversation input;

build trusted Meta channel context;

invoke the existing commerce runtime;

use the inbound wamid-derived request ID for business idempotency;

require a non-empty approved final response;

atomically mark inbound completed and create outbound row; and

release lock.

If processing crashes after a commerce write but before inbox completion, lease retrymust reuse the same request identity so side effects remain safe.

Never rerun the agent merely because outbound sending failed. The exact generated replyis already persisted and is retried/dispositioned independently.

17. Meta Outbound Provider Contract

Implement the existing provider abstraction with Meta-specific infrastructure:

class MetaWhatsAppMessageProvider(OutboundMessageProvider):
    async def send_text(
        self,
        recipient_id: str,
        body: str,
        local_message_id: UUID,
    ) -> ProviderMessageResult: ...

    async def send_template(
        self,
        recipient_id: str,
        template: ApprovedMetaTemplateMessage,
        local_message_id: UUID,
    ) -> ProviderMessageResult: ...

If the shared interface becomes message-kind based, keep provider-specific SDK/HTTPtypes inside infrastructure and expose one typed provider-neutral request.

Graph endpoint:

POST https://graph.facebook.com/{GRAPH_API_VERSION}/{PHONE_NUMBER_ID}/messages

Required headers:

Authorization: Bearer <access-token>
Content-Type: application/json

Free-form text payload meaning:

{
  "messaging_product": "whatsapp",
  "recipient_type": "individual",
  "to": "919560717170",
  "type": "text",
  "text": {
    "preview_url": false,
    "body": "Approved response text"
  }
}

Rules:

Convert canonical E.164 recipient to Meta's required digits-only representation atthis boundary.

Validate recipient and body length before network I/O.

Send the persisted body exactly; do not invoke the Response Node again.

Disable URL preview unless explicitly approved.

Apply bounded connect/read/total timeouts.

Parse success defensively and require a returned provider message ID.

Store the returned wamid immediately after acceptance.

Never log request authorization, full recipient, full body, or raw provider response.

Local message UUID is an internal deduplication/trace key; do not claim Meta honors itas a provider idempotency key unless the selected API explicitly documents thatbehavior.

18. Template Messages

Free-form conversational replies are allowed only within Meta's applicablecustomer-service window. Business-initiated messages outside that window require anapproved template.

Template selection remains deterministic:

notification type + locale + template version
    -> reviewed internal template key
    -> configured Meta template name/language/components

Rules:

The LLM never selects a Meta template name or constructs arbitrary components.

Only configured, approved templates may be sent.

Template parameters come from approved notification payload fields.

Preserve order references, amounts, quantities, units, and statuses exactly.

Validate parameter count/type before enqueue/send.

Do not store or send payment credentials or sensitive unrestricted values.

If no approved template exists outside the window, mark the outbound/notification asTEMPLATE_REQUIRED or SUPPRESSED under existing policy; do not send free-form text.

The Meta hello_world template is acceptable for setup verification only, not ordernotifications.

19. Customer-Service Window

Update the channel conversation's trusted last_inbound_at for every valid supportedinbound customer message. Determine free-form eligibility using server receipt time andconfigured Meta policy window, not a user-controlled timestamp.

Before outbound dispatch:

if now - last_inbound_at is within configured window:
    TEXT may be sent
else:
    require approved TEMPLATE

Rules:

Immediate agent replies normally use text.

A queued message can cross the window before dispatch; re-evaluate at send time.

An inbound message reopens/refreshes the service window under provider policy.

Do not extend the window based on delivery/read callbacks or outbound messages.

Keep the window configurable for testing but default to the current Meta policy usedby the integration.

20. Outbound Failure Classification

Provider errors map into existing typed categories:

MetaRetryableSendError
MetaPermanentSendError
MetaAmbiguousSendError

Retryable

Examples:

HTTP 429/rate limiting with bounded backoff;

provider 5xx;

documented temporary Meta error code;

connection failure known to occur before request acceptance;

recoverable lease expiration before send.

Permanent

Examples:

invalid recipient format;

invalid body/template payload;

missing or unapproved template;

authentication/permission/configuration failure requiring operator action;

unsupported message kind;

documented permanent provider rejection.

Ambiguous

Timeout or connection loss after the request may have reached Meta is ambiguous. Sinceblind retries may send duplicate WhatsApp messages and the send endpoint may not honor alocal idempotency key:

mark outbound AMBIGUOUS;

persist safe error category and operational alert;

do not automatically send again unless an explicit reconciliation/provider guaranteemakes it safe;

never rerun the commerce agent;

expose controlled operator resolution later.

Classify using HTTP status plus bounded documented Meta error code/subcode. Do not storeor surface unrestricted provider error messages to customers.

21. Retry, Lease, and Dead-Letter Policy

Use existing PostgreSQL FOR UPDATE SKIP LOCKED/lease claiming semantics.

Exponential backoff with jitter remains bounded.

Attempt counts increment atomically with state transitions.

One worker owns a leased row at a time.

A retryable message moves back to claimable state at next_attempt_at.

Exhausted retryable attempts move to DEAD_LETTER.

Permanent failures move to FAILED without retry.

Ambiguous sends move to AMBIGUOUS without blind retry.

A stored provider wamid prevents another normal send attempt.

Worker restart must recover expired leases.

Provider failure never causes order or payment state rollback.

22. Delivery Status Processing

Normalize Meta statuses:

Meta status

Internal status

API accepted response

ACCEPTED

sent

SENT

delivered

DELIVERED

read

READ

failed

FAILED

unknown signed status

safely ignored/recorded as unsupported metric

Rules:

Find outbound by channel and provider wamid.

A status for an unknown wamid is persisted in a bounded orphan/event strategy orsafely counted for reconciliation; it never creates an order/conversation.

Store each distinct status event idempotently.

Apply monotonic progress:

ACCEPTED < SENT < DELIVERED < READ

Repeated/lower progress does not regress current outbound state.

FAILED stores a bounded provider error code/category and provider event time.

Define terminal/conflict handling explicitly when delayed statuses arrive; preserveimmutable event history even when current-state projection does not change.

Delivery callbacks never enter conversation messages or change commerce/order status.

Provider timestamps are metadata; server receipt time remains separately recorded.

23. Notification Integration

Specification 019 remains channel-neutral. Update its active provider assumptions:

preferred_channel=whatsapp resolves through the provider persisted on the outboundrow; new outbound rows use the configured active WhatsApp provider.

Notification processor renders deterministic reviewed content.

Inside the service window, permitted notification text may use free-form TEXT underpolicy.

Outside the service window, use configured approved Meta TEMPLATE.

Missing template mapping suppresses/fails safely; it never asks an LLM to improvise.

Notification outbox event, channel outbound row, provider acceptance, and deliveryevent remain separate durable lifecycle records.

Order/payment transaction never waits for Meta.

24. Response Localization

The existing Response Node continues to produce immediate agent replies in thecustomer's latest language, script, tone, and chat style.

Persist and send the exact approved final response.

Preserve Unicode and intended newlines.

Apply Meta length limits before send; do not silently truncate business values.

If a response exceeds supported length, use a deterministic safe segmentation orfailure policy defined and tested centrally. Do not split in the middle of product,price, quantity, unit, option, or required question meaning.

Provider/webhook/retry language never appears in customer-facing messages.

Proactive notification templates use reviewed locale mappings rather than dynamic LLMtranslation.

25. Privacy and Data Handling

WhatsApp sender identifiers and message bodies are personal data.

Store only fields required for conversation, delivery, troubleshooting, consent, andconfigured retention.

Do not persist the complete raw webhook body by default.

Never log full phone numbers, access tokens, App Secrets, verification tokens,signatures, full message bodies, delivery addresses, or profile data.

Use masked/hashed identifiers for correlation where appropriate.

contacts.profile.name is untrusted metadata and not long-term profile truth.

Data deletion must cover Meta channel mappings/messages under the project's customerdeletion policy while preserving legally required order/audit records appropriately.

Test data follows configured short retention and must not be treated as anonymous.

Health/metrics endpoints reveal no WABA, Phone Number ID, recipient, or credential.

26. Application Wiring

Recommended ownership:

app/api/meta_whatsapp_webhooks.py
app/jobs/channel_workers.py                 # generalized existing workers
channels/models.py
channels/providers.py
channels/services/
infrastructure/channels/meta/
  message_provider.py
  signature_validator.py
  webhook_parser.py
infrastructure/database/repositories/
  postgres_channel_repository.py
app/config/settings.py
app/application_container.py

Rules:

Keep Meta HTTP/payload types inside the adapter/infrastructure boundary.

Reuse channel-neutral domain/application models.

Generalize Twilio-named worker constants/types only where necessary; do not duplicatethe full worker pipeline for Meta.

Initialize Meta provider/validator only when enabled.

Start workers after database and provider wiring succeeds.

Stop/await workers before closing shared HTTP/database resources.

One worker iteration failure must not permanently stop later iterations.

Use one reusable async HTTP client with connection pooling and clean shutdown.

27. Health and Readiness

/health/live remains process liveness.

/health/ready should verify without sending a WhatsApp message:

database connectivity;

required Meta configuration syntactically present when enabled;

inbound/outbound worker running and recently successful under established threshold;

required repository/migration readiness;

provider HTTP client initialized.

Do not call Meta on every readiness probe. A separate controlled diagnostic command mayvalidate token/resource access without sending, subject to provider API support and ratepolicy.

Readiness response uses safe component states only and never includes secrets or fullresource identifiers.

28. Observability

Low-cardinality metrics:

channel_webhooks_total{channel,event_type,outcome}
channel_inbound_messages_total{channel,kind,outcome}
channel_outbound_messages_total{channel,kind,outcome}
channel_delivery_events_total{channel,status}
channel_retries_total{channel,direction,outcome}
channel_worker_health{channel,worker}
channel_processing_latency_seconds{channel,direction}
channel_ambiguous_sends_total{channel}

Rules:

Channel label is whatsapp; provider label is the bounded selected value such asmeta_cloud or twilio only where provider comparison is operationally useful.

Do not label metrics with phone number, wamid, WABA ID, Phone Number ID, templateparameter, customer/profile name, conversation/order ID, or error message.

Structured logs use safe internal IDs and bounded categories.

Invalid signature attempts are observable without payload leakage.

Alert on worker health failure, dead-letter growth, ambiguous sends, repeated authfailures, signature failures above baseline, and delivery-failure spikes.

29. Local Development and Test Setup

Start PostgreSQL and apply Alembic migrations.

Configure Meta environment values without committing them.

Start FastAPI on 0.0.0.0.

Expose the local port through a trusted HTTPS tunnel.

Set Meta callback URL and verification token.

Complete GET verification.

Subscribe to the messages field.

Send a WhatsApp text from the verified recipient to the test number.

Confirm:

webhook HTTP 200
-> one inbox row
-> worker processes it
-> one persisted outbound row
-> Graph API returns wamid
-> customer receives response
-> status events progress

Replay the same webhook fixture and confirm no duplicate agent/business effect.

When a tunnel URL changes, update Meta callback configuration and the backend publicbase setting. The HMAC signature is over body bytes, not the URL, but verification andoperational configuration must still reference the active callback.

30. Testing Requirements

30.1 Provider selection tests

disabled creates no WhatsApp provider/workers and requires no provider secrets.

twilio creates only Twilio components and validates only Twilio-required settings.

meta_cloud creates only Meta components and validates only Meta-required settings.

Invalid provider value fails startup.

Unselected provider webhook performs no write and returns 404.

Workers operate through interfaces without provider-name branches.

New outbound row persists the active provider.

Dispatcher routes a persisted provider row only to its matching adapter.

Provider switch with unresolved old-provider rows is blocked or requires an explicitdisposition policy.

Commerce runtime behavior is identical across provider selection.

30.2 Verification tests

Correct mode/token returns exact challenge as plain text.

Wrong/missing token or mode returns 403.

Verification creates no database rows.

Tokens/challenges do not appear in logs.

30.3 Signature and parser tests

Correct HMAC over exact raw body is accepted.

Missing, malformed, wrong, and body-altered signatures are rejected before writes.

Re-serialized JSON produces a different signature and is not used for verification.

Oversized body/content type/malformed signed JSON use safe status behavior.

Wrong WABA or Phone Number ID is rejected/ignored under documented safe policy.

Multiple entries/changes/messages/statuses parse correctly.

Unknown signed fields/types do not crash the route.

Raw payload and secrets remain absent from logs.

30.4 Inbound tests

Supported text creates one inbox row with canonical sender and exact normalized text.

Duplicate wamid is acknowledged but creates no duplicate row/reply/effect.

Empty and non-text message creates one unsupported flow.

Profile display name never becomes saved delivery name automatically.

Meta sender resolves stable conversation across messages.

Meta and Twilio provider records do not merge implicitly; intentionally normalizedWhatsApp conversation mappings may survive a controlled provider switch.

Tenant/conversation cannot be overridden by payload fields.

30.5 Runtime idempotency tests

Duplicate/replayed add-to-cart inbound cannot duplicate cart mutation.

Duplicate/replayed confirm-order inbound cannot create a second order.

Crash after commerce effect and before inbox completion retries safely with samerequest ID.

Outbound failure never reruns planner/runtime.

Conversation lock preserves message order for the same customer.

30.6 Outbound provider tests

URL includes configured pinned Graph version and Phone Number ID.

Authorization header is present in request and absent from logs.

E.164 converts to valid Meta digits-only recipient.

Text and approved template payloads serialize exactly.

Missing returned wamid becomes ambiguous/safe failure.

HTTP 429/5xx/documented temporary errors retry with bounded policy.

Invalid payload/auth/permission/template errors become permanent/operator failures.

Timeout after possible acceptance becomes ambiguous and is not blindly resent.

Provider success stores wamid before another claim can send normally.

30.7 Service-window/template tests

Immediate response inside window uses text.

Queue delay crossing window triggers re-evaluation.

Outside window with approved mapping uses template.

Outside window without mapping becomes template-required/suppressed.

hello_world is never selected for business notifications.

Template parameter validation preserves approved business values.

30.8 Status tests

sent, delivered, read, and failed map correctly.

Duplicate status webhook is idempotent.

Out-of-order lower state does not regress current projection.

Immutable event history is retained.

Unknown wamid is handled safely without creating commerce data.

Status callback never enters conversation or changes order status.

30.9 Worker/repository tests

Concurrent workers do not double-claim rows.

Expired leases recover.

Retry schedules and attempts are durable.

Exhaustion reaches dead letter.

Permanent and ambiguous outcomes do not enter ordinary retry loop.

Shutdown awaits worker cancellation before database/HTTP client close.

REST channel remains functional when Meta is enabled or disabled.

30.10 End-to-end test-number acceptance

Using synthetic/non-sensitive test data:

Customer sends Hi to Meta test number.

Webhook persists and acknowledges quickly.

Existing onboarding/profile flow responds in customer style.

Returning message restores same conversation.

Product/cart/checkout flow completes without duplicate effects.

Outbound message receives provider wamid.

Sent/delivered/read callbacks update delivery state.

Duplicate inbound/status fixtures remain harmless.

Invalid-signature fixture creates no trusted record.

Token expiry/auth failure produces safe operational failure without leaking secret.

31. Acceptance Criteria

This milestone is complete when:

Meta successfully verifies the configured GET webhook.

Every trusted POST is HMAC-validated over raw bytes before durable effects.

Valid text from the verified recipient creates one durable Meta inbox row and stableMeta conversation mapping.

Webhook acknowledgement does not wait for Gemini, LangGraph, commerce SQL beyond therequired inbox persistence, or outbound Graph API.

Existing worker/runtime produces and persists one localized response.

Meta provider sends the persisted response and records returned wamid.

Sent, delivered, read, and failed events are durable, idempotent, and monotonic.

Duplicate inbound delivery cannot duplicate cart/order/profile effects.

Unsupported messages receive one deterministic text response without media download.

Customer-service window and approved-template rules are enforced at dispatch.

Ambiguous sends are not blindly retried.

Meta credentials, signatures, full identifiers, and raw payloads do not enterprompts, logs, metrics, or health responses.

Twilio history remains intact and provider selection can switch betweentwilio, meta_cloud, and disabled without commerce-code changes.

REST/web channels and customer graph remain unchanged.

Migrations, unit, integration, security, concurrency, worker, and live test-numberacceptance tests pass.

32. Recommended Implementation Order

Confirm direct Meta test-number template send and record non-secret IDs/configuration.

Add WHATSAPP_PROVIDER, provider factory/registry, provider-neutral channel enum,provider persistence, and migration changes.

Implement GET verification route and tests.

Implement raw-body HMAC validator and security tests.

Implement bounded webhook parser/normalizer for text, unsupported types, and statuses.

Integrate Meta events into existing channel repository/deduplication.

Generalize worker/channel wiring without duplicating the runtime pipeline.

Implement async Meta text provider with typed retryable/permanent/ambiguous errors.

Implement delivery-event projection and monotonic status processing.

Implement service-window enforcement and reviewed template-provider contract.

Update notification routing to whatsapp and persist the selected provider on eachnew outbound row.

Add health, metrics, safe logging, alerts, and graceful lifecycle wiring.

Configure public HTTPS callback, verify subscription, and subscribe to messages.

Run fixture replay, failure injection, concurrency, and live test-recipientacceptance.

Keep Twilio disabled; schedule cleanup only after a stable Meta pilot.

33. Follow-up Milestones

After this specification:

Replace temporary token with securely managed production system-user credentials.

Complete business verification and production phone-number onboarding when thebusiness is established.

Create/review/approve production order-notification templates and locale mappings.

Add controlled media support only when a concrete customer workflow requires it.

Add human-agent handoff/inbox if operational support needs it.

Resume customer department/category guided-shopping work after the channel is stable.

Complete production deployment, backup, recovery, privacy, and security hardening.
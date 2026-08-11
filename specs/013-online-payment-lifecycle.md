Online Payment Lifecycle and Fake Provider Specification

1. Purpose

Add an optional online-payment flow without requiring a merchant account or connectingto a real payment processor.

The first implementation uses a provider-neutral PaymentProvider contract and adevelopment-only FakePaymentProvider. The design must allow a futureRazorpayPaymentProvider to be added without changing planner, checkout, order,inventory, or response-domain rules.

Cash on Delivery remains fully supported and behaviorally unchanged.

2. Frozen Architecture

The customer graph remains:

Planner -> Execute -> Response -> END

Do not add a payment node to LangGraph.

The planner chooses one capability; it never creates or settles payments.

Capabilities validate typed intent and call application/domain services.

Commerce services own payment and order state-transition rules.

Provider adapters own external payment-provider communication.

PostgreSQL is authoritative for carts, orders, payment attempts, webhook events,inventory, and reservations.

LangGraph checkpoints store messages and short-term CommerceSession, neverauthoritative payment state.

Trusted tenant_id, conversation_id, request identity, and webhook configurationnever come from LLM capability arguments.

The Response Node localizes only approved execution outcomes.

3. Goals

Let the customer explicitly choose CASH_ON_DELIVERY or ONLINE.

Create a fake hosted-payment session through a provider-neutral interface.

Reserve stock before the customer leaves to pay.

Confirm an online order only after a verified successful provider event.

Release inventory after payment failure, expiry, cancellation, or timeout.

Process duplicate and out-of-order webhooks safely.

Reconcile payments when webhooks are missed.

Let the customer query current payment/order status.

Preserve all existing stock, cart-version, tenant-isolation, and localization rules.

Provide deterministic development endpoints to simulate payment outcomes.

4. Non-Goals

Real money movement or merchant settlement.

Razorpay, Stripe, or another production provider integration.

Card, bank-account, UPI, CVV, or payment credential storage.

Refund transfer to a real payment instrument.

Partial capture, split payment, EMI, subscriptions, tips, or saved payment methods.

LLM interpretation of provider webhook payloads.

Treating browser redirect/query parameters as proof of payment.

Changing staff fulfilment transitions.

5. Payment and Order Policy

5.1 Payment methods

class PaymentMethod(str, Enum):
    CASH_ON_DELIVERY = "CASH_ON_DELIVERY"
    ONLINE = "ONLINE"

COD continues through the existing explicit confirmation transaction.

Online payment uses a provisional order because existing inventory reservations areowned by order_id and historical item/price snapshots must be immutable.

5.2 Order statuses

Extend the order lifecycle with pre-fulfilment payment states:

class OrderStatus(str, Enum):
    AWAITING_PAYMENT = "AWAITING_PAYMENT"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    PAYMENT_EXPIRED = "PAYMENT_EXPIRED"
    CONFIRMED = "CONFIRMED"
    PREPARING = "PREPARING"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"

Rules:

Staff fulfilment starts only from CONFIRMED.

AWAITING_PAYMENT, PAYMENT_FAILED, and PAYMENT_EXPIRED are not confirmed orders.

Provider success changes AWAITING_PAYMENT to CONFIRMED transactionally.

Provider failure/expiry releases active reservations and moves to the matching status.

A failed/expired online order may be retried using a new payment attempt on the sameorder after stock is revalidated and reserved again.

An online order may switch to COD only through an explicit customer capability thatrevalidates stock and transitions the same provisional order; it must not create asecond order for the same source cart.

orders.source_cart_id remains unique and is the order-creation idempotency boundary.

5.3 Cart policy

When the provisional online order is created successfully:

create immutable order-item snapshots;

create active inventory reservations;

set the source cart to CHECKED_OUT; and

make the provisional order the durable recovery object.

Do not leave a mutable active cart behind a payment session. Payment retries operate onthe existing provisional order, not by recreating a cart or order.

If provisional-order creation fails before commit, the cart remains ACTIVE and noorder, payment attempt, or reservation survives.

6. Domain Models

6.1 Payment attempt

class PaymentAttemptStatus(str, Enum):
    CREATING = "CREATING"
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class PaymentAttempt(BaseModel):
    id: UUID
    tenant_id: UUID
    order_id: UUID
    provider: str
    provider_payment_id: str | None
    idempotency_key: str
    amount: Decimal
    currency: str
    status: PaymentAttemptStatus
    checkout_url: str | None
    expires_at: datetime
    failure_code: str | None
    created_at: datetime
    updated_at: datetime

Rules:

Amount and currency come from immutable order-item snapshots.

Amount uses Decimal; never calculate through binary floating point.

One idempotency key identifies one logical create-payment request.

Provider IDs and URLs are provider output, never LLM-generated values.

Store only provider references and customer-safe error categories, not paymentcredentials or unrestricted raw payloads.

6.2 Webhook event

class PaymentWebhookEvent(BaseModel):
    id: UUID
    provider: str
    provider_event_id: str
    provider_payment_id: str
    event_type: str
    payload_hash: str
    processing_status: WebhookProcessingStatus
    received_at: datetime
    processed_at: datetime | None
    failure_reason: str | None

The database must enforce uniqueness on (provider, provider_event_id).

6.3 Refund representation

REFUNDED is not required in the first fake-provider customer flow because no realfunds move. Reserve schema/enum support only if the existing order cancellation designneeds it. Do not report a monetary refund unless a provider-confirmed refund exists.

7. Provider-Neutral Contract

Define the interface outside commerce domain logic:

class PaymentProvider(Protocol):
    @property
    def name(self) -> str: ...

    async def create_checkout(
        self,
        request: CreateProviderCheckoutRequest,
    ) -> ProviderCheckout: ...

    async def verify_and_parse_webhook(
        self,
        raw_body: bytes,
        signature: str,
    ) -> VerifiedPaymentEvent: ...

    async def get_payment_status(
        self,
        provider_payment_id: str,
    ) -> ProviderPaymentStatus: ...

Provider request:

class CreateProviderCheckoutRequest(BaseModel):
    merchant_reference: str
    idempotency_key: str
    amount: Decimal
    currency: str
    expires_at: datetime
    return_url: str

The provider contract must not receive cart, customer address, conversation messages,planner state, or unrestricted domain objects unless a real provider later requires areviewed, minimal field.

Provider exceptions must map into typed categories such as temporary unavailable,invalid response, timeout, and configuration error. Do not leak provider exceptions tocustomers.

8. Fake Payment Provider

8.1 Configuration

PAYMENT_PROVIDER=fake
FAKE_PAYMENT_WEBHOOK_SECRET=replace-with-a-random-development-secret
FAKE_PAYMENT_BASE_URL=http://localhost:8000
PAYMENT_ATTEMPT_TTL_MINUTES=15
PAYMENT_RECONCILIATION_BATCH_SIZE=100

Fail startup if PAYMENT_PROVIDER=fake and the webhook secret is missing or a knownplaceholder outside automated tests.

The fake provider must be disabled in production unless an explicit safe deploymentpolicy permits it. Prefer failing startup for APP_ENV=production withPAYMENT_PROVIDER=fake.

Secrets come only from environment-backed settings and must never appear in logs,prompts, responses, or database payload columns.

8.2 Fake checkout

create_checkout creates an internal provider payment record and returns:

a unique provider_payment_id;

status PENDING;

an application-local fake checkout URL; and

its expiry time.

No real payment form or credential entry is required. A minimal development page mayshow order reference and amount with buttons to simulate success, failure, or expiry.

8.3 Development simulation endpoints

Expose environment-gated development routes such as:

POST /dev/payments/{provider_payment_id}/succeed
POST /dev/payments/{provider_payment_id}/fail
POST /dev/payments/{provider_payment_id}/expire

These routes must:

be unavailable outside development/test;

resolve only fake-provider records;

create a unique fake provider event;

sign the raw event body with HMAC-SHA256 using the configured secret; and

pass the event through the same webhook ingestion/application path used by a futureexternal provider.

They must not update orders, attempts, or inventory directly.

8.4 Webhook signature

Use a documented canonical HMAC format over the exact raw request bytes. Verify with aconstant-time comparison before parsing or processing the event.

Reject missing, malformed, or invalid signatures with an appropriate HTTP error and nodurable business mutation. Never ask the LLM to verify or interpret a webhook.

9. PostgreSQL Schema

Add application-owned tables/columns with Alembic.

9.1 payment_attempts

Column

Type

Rule

id

UUID

Primary key

tenant_id

UUID

Required

order_id

UUID

Required foreign key

provider

text

Required

provider_payment_id

text

Nullable until provider creation succeeds

idempotency_key

text

Required

amount

numeric

Required and positive

currency

text

Required

status

text

Required

checkout_url

text

Nullable

expires_at

timestamptz

Required

failure_code

text

Nullable customer-safe category

created_at

timestamptz

Required

updated_at

timestamptz

Required

Required constraints:

UNIQUE (tenant_id, idempotency_key)
UNIQUE (provider, provider_payment_id)
CHECK (amount > 0)
INDEX (tenant_id, order_id, created_at DESC)
INDEX (status, expires_at)

Use a partial unique index if only one PENDING attempt may exist per order.

9.2 payment_webhook_events

Column

Type

Rule

id

UUID

Primary key

provider

text

Required

provider_event_id

text

Required

provider_payment_id

text

Required

event_type

text

Required

payload_hash

text

Required

processing_status

text

Required

received_at

timestamptz

Required

processed_at

timestamptz

Nullable

failure_reason

text

Nullable bounded category

Required constraints:

UNIQUE (provider, provider_event_id)
INDEX (processing_status, received_at)

Do not persist secrets, card data, unrestricted headers, or unnecessary full rawpayloads. If raw webhook retention is needed later, define encryption, access, andretention policy first.

9.3 Existing tables

Extend orders.payment_method to allow ONLINE.

Extend orders.status with payment states.

Add timestamps only where useful, such as payment_confirmed_at.

Preserve unique orders.source_cart_id.

Reuse existing order-owned inventory reservation tables and idempotency constraints.

10. Online Checkout Creation Flow

Add a capability such as start_online_payment requiring no provider-controlled oridentity arguments. The payment method must have been explicitly selected by thecustomer in the current checkout review.

10.1 Transaction A: provisional order and reservation

In one database transaction:

resolve trusted tenant, conversation, source cart, and expected cart version;

return an existing source-cart order when idempotently applicable;

lock and validate the tenant-scoped active cart;

verify complete delivery details and explicit online-payment intent;

lock inventory rows in deterministic product-ID order;

revalidate all stock under the existing stock-recovery rules;

create one AWAITING_PAYMENT order and immutable items;

create active order-owned inventory reservations;

mark the cart CHECKED_OUT;

create a local CREATING payment attempt with a unique idempotency key; and

commit.

If stock is insufficient, create nothing and return the existing stock-recovery outcome.

10.2 Provider call

After Transaction A commits, call PaymentProvider.create_checkout using the localattempt's idempotency key and immutable amount.

Do not keep a database transaction open during the provider call.

10.3 Transaction B: persist provider result

In a new transaction:

lock the attempt;

if already PENDING or terminal, return its current result idempotently;

persist provider payment ID, checkout URL, expiry, and PENDING; or

on a definitive provider-creation failure, mark the attempt FAILED, releasereservations, and set order PAYMENT_FAILED.

For an ambiguous timeout, keep the attempt recoverable as CREATING; reconciliationmust query by provider/idempotency reference before creating another attempt.

10.4 Customer response

Return only approved data:

exact amount and currency;

payment status;

fake checkout URL or safe action token; and

expiry time when approved.

Never claim payment success from checkout creation.

11. Webhook Processing

Webhook handling is a deterministic FastAPI/application path, not a planner capability.

11.1 Ingestion

Read exact raw request bytes.

Verify signature using the selected provider adapter.

Parse into VerifiedPaymentEvent.

Insert the provider event using unique (provider, provider_event_id).

If already present, return successful acknowledgement without reapplying effects.

11.2 Success event transaction

In one transaction:

lock webhook event, payment attempt, order, and its reservations;

verify provider payment identity, expected amount, and currency;

if attempt/order already succeeded/confirmed, mark event processed idempotently;

require the order to be in an allowed pre-confirmation state;

set attempt SUCCEEDED;

set order CONFIRMED and payment_confirmed_at;

keep reservations ACTIVE for the existing fulfilment lifecycle;

record the order-status history transition as a system/provider action; and

mark the webhook event processed.

A return URL, browser redirect, planner message, or development button alone must neverconfirm the order.

11.3 Failure or expiry event transaction

In one transaction:

lock event, attempt, order, and reservations;

idempotently set attempt to FAILED or EXPIRED;

release active reservations exactly once;

set order to PAYMENT_FAILED or PAYMENT_EXPIRED unless already confirmed;

record status history; and

mark the event processed.

A late failure/expiry event must never demote a succeeded payment or confirmed order.

11.4 Out-of-order events

Use a monotonic transition policy:

SUCCEEDED is terminal for a payment attempt in this milestone.

Failure/expiry after success is recorded as ignored, not applied.

Success after local expiry requires authoritative provider status verification beforeconfirmation. If provider confirms success, process success and alert on any alreadyreleased reservation conflict.

Unknown attempt/provider payment IDs are stored or quarantined safely forreconciliation without leaking information.

12. Payment Retry and Switching to COD

12.1 Retry online payment

Add retry_online_payment for an existing tenant/conversation-scoped provisional order.

It must:

reject retry when already confirmed, cancelled, or delivered;

return an existing non-expired pending attempt instead of creating another;

lock inventory and revalidate the original immutable order quantities;

recreate active reservations if they were released;

return stock-recovery meaning if inventory is no longer available;

create a new idempotent payment attempt; and

use the same provider-call split transaction pattern.

Do not silently change quantities, products, prices, currency, or delivery details on apayment retry.

12.2 Switch to COD

Add switch_order_to_cash_on_delivery only on explicit customer intent.

In one transaction:

lock the provisional order and attempts;

verify no payment has succeeded;

revalidate/recreate inventory reservations when required;

set payment_method=CASH_ON_DELIVERY;

set order CONFIRMED;

preserve the same order ID and source cart;

record status history; and

prevent future pending attempts from confirming independently.

If payment status is ambiguous, reconcile first and do not switch until the system canexclude payment success.

13. Payment Status Capability

Add view_payment_status requiring no provider or payment ID from the LLM. Resolve therelevant order from trusted conversation state or the current recent-order selection.

Customer-safe statuses:

waiting for payment;

payment successful and order confirmed;

payment failed;

payment expired;

temporary status unavailable.

Never expose provider secrets, internal event IDs, raw failure payloads, or databasestate. A status query performs no payment transition unless it explicitly invokes thedeterministic reconciliation service under policy.

14. Reconciliation

Implement a deterministic scheduled application job outside LangGraph.

It selects bounded batches of:

CREATING attempts older than a short grace period;

PENDING attempts near/past expiry; and

webhook events in retryable processing states.

For each attempt:

query PaymentProvider.get_payment_status;

convert provider status to the same verified internal event model;

process it through the same idempotent transition service as webhooks; and

record bounded retry/next-attempt metadata under the project's job policy.

The job must use database coordination so multiple application instances do not processthe same row concurrently, such as FOR UPDATE SKIP LOCKED or an equivalent lease.

Do not implement reconciliation with conversation messages or the planner.

15. Capabilities and Planner Routing

Required capabilities:

select_payment_method

start_online_payment

retry_online_payment

switch_order_to_cash_on_delivery

view_payment_status

select_payment_method accepts only a closed enum. Provider name, amount, currency,payment ID, webhook event, success flag, and checkout URL are never LLM arguments.

Mandatory planner rules:

Execute select_payment_method when the customer explicitly chooses COD or online.

Start online payment only after a complete checkout review and explicit confirmation.

Never execute existing COD confirmation when online payment is selected.

Never interpret I paid, screenshots, redirect text, or a customer-provided paymentID as payment success.

A request for status executes view_payment_status.

A retry request executes retry_online_payment only for the current eligible order.

Switching to COD requires explicit customer intent.

Never let the customer choose the provider in this milestone; configuration selectsfake.

One planner decision/capability per turn remains mandatory.

All routing rules apply across languages, scripts, informal spellings,transliteration, and mixed-language messages.

16. Approved Outcomes and Localization

Recommended stable IDs:

Meaning

Fragment/follow-up ID

Payment method selected

payment-method-selected

Payment ready

online-payment-ready

Waiting for payment

payment-pending

Payment succeeded

payment-succeeded

Payment failed

payment-failed

Payment expired

payment-expired

Provider temporarily unavailable

payment-temporarily-unavailable

Retry offered

retry-online-payment

Switch to COD offered

offer-cash-on-delivery

Switched to COD

switched-to-cash-on-delivery

Status unknown

payment-status-unavailable

Response rules:

Use only approved fragments, follow-up, and options as source meaning.

Match the latest customer's language, script, tone, and chat style.

Preserve exact amount, currency, order reference, provider-approved URL, and expirytime when included.

Never translate or modify URLs, identifiers, amounts, or currency codes.

Never say paid, successful, or confirmed before the durable verified transition.

Ask exactly one clear question when a follow-up exists.

Deterministic fallback must preserve all approved IDs and meanings in order.

17. Idempotency and Concurrency

Every side-effecting payment command uses a trusted application-generatedidempotency key.

Provider checkout creation receives the same key.

Webhook events are unique by provider event ID.

Provider payments are unique by provider and provider payment ID.

Source cart creates at most one order.

An order has at most one non-expired pending payment attempt.

Reservation creation, release, and fulfilment consumption remain idempotent.

Lock order consistently across order, attempt, and reservation operations.

Reuse the existing confirmation-only retry policy only for documented PostgreSQL40P01 and 40001 failures where the entire transaction can safely restart.

Never retry validation, stock shortage, invalid signature, provider-declared failure,or other business outcomes.

18. Security and Privacy

Verify webhooks before trusting parsed event fields.

Use constant-time signature comparison.

Keep secrets in environment-backed settings.

Require HTTPS for any future non-local provider integration.

Never store card data, CVV, bank credentials, UPI PIN, or unrestricted payment forminput.

Never send payment secrets or raw webhook bodies to the LLM.

Do not log signatures, secrets, full checkout URLs with sensitive query parameters,delivery PII, or raw provider payloads.

Scope customer payment/order queries by trusted tenant and conversation/customercontext.

Development simulation endpoints must be unavailable in production.

Apply rate limiting to fake simulation and webhook endpoints in shared developmentenvironments.

19. Failure Handling

Invalid webhook signature: reject with no business mutation.

Duplicate webhook: acknowledge idempotently.

Unknown provider payment: quarantine for reconciliation; do not create an order.

Amount/currency mismatch: do not confirm; record a security/operations alert.

Provider timeout during creation: preserve CREATING and reconcile before retrying.

Provider definitive creation failure: release reservation and mark payment/orderfailed transactionally.

Stock shortage at initial creation/retry: return existing recovery UX and create nonew attempt.

Database error: roll back the current transaction and return/record a safe failure.

Webhook processing failure after event insert: leave it retryable for reconciliation.

Response composition failure: use deterministic approved fallback.

20. Testing Requirements

20.1 Provider contract tests

Fake checkout creation is idempotent by provider request key.

Fake provider returns deterministic pending/success/failure/expiry states.

Valid HMAC webhooks verify; tampered body/signature fails.

Status lookup returns authoritative fake-provider state.

A future provider adapter can pass the same contract suite.

20.2 Order/payment service tests

COD behavior remains unchanged.

Online creation makes one AWAITING_PAYMENT order, item snapshots, reservation, andpayment attempt.

Stock shortage creates none of those records and keeps the cart active.

Provider success confirms the order and retains active reservation.

Failure/expiry releases reservation once and marks matching states.

Retry revalidates stock and does not change order snapshots.

Switch to COD preserves the order ID and cannot occur after payment success.

A provisional order never enters staff fulfilment.

20.3 Webhook/idempotency tests

Duplicate event processes side effects once.

Different event IDs carrying the same terminal status remain harmless.

Failure after success cannot demote an order.

Success after expiry follows authoritative late-success policy.

Amount/currency mismatch never confirms.

Concurrent success events create one status transition.

Transaction rollback leaves event retryable and avoids partial effects.

20.4 Reconciliation tests

Missed success webhook is recovered by polling.

Stuck CREATING attempt resolves without duplicate provider payment.

Expired pending attempts release reservations.

Multiple workers claim different rows safely.

Repeated reconciliation is idempotent.

20.5 Planner/response/integration tests

English, Hindi, Romanized Hindi, and mixed-language payment intents route correctly.

Customer claims never mark payment successful.

Provider-controlled values never appear in LLM arguments.

Fake success endpoint travels through verified webhook processing.

Full online flow reaches CONFIRMED exactly once.

Full failure and retry flow recovers safely.

Guest and saved-delivery-detail checkout both work.

Customer-facing output is grounded, localized, and deterministic on fallback.

21. Implementation Placement

Adapt paths to current repository conventions:

commerce/models/payment.py
commerce/repositories/payment_repository.py
commerce/services/payment_service.py
commerce/services/payment_event_service.py
runtime/capabilities/select_payment_method/
runtime/capabilities/start_online_payment/
runtime/capabilities/retry_online_payment/
runtime/capabilities/switch_order_to_cash_on_delivery/
runtime/capabilities/view_payment_status/
infrastructure/payments/provider.py
infrastructure/payments/fake_provider.py
infrastructure/database/repositories/postgres_payment_repository.py
app/api/payment_webhooks.py
app/api/dev_fake_payments.py
app/jobs/payment_reconciliation.py
alembic/versions/
tests/unit/
tests/integration/

Keep provider SDK/types outside commerce models. Keep SQL outside capabilities andprompt text outside services.

22. Definition of Done

This milestone is complete when:

COD passes all existing tests unchanged;

online payment uses the provider-neutral interface and fake adapter;

provisional order, immutable items, reservations, and local attempt are createdatomically;

verified webhook success is the only fake-provider path that confirms online payment;

failure/expiry releases stock idempotently;

duplicate, concurrent, late, and missed events are handled safely;

payment retries and explicit COD switching preserve one source-cart order;

fake simulation endpoints and secrets are environment-gated;

reconciliation uses the same idempotent transition service;

no sensitive payment or delivery data reaches prompts or logs;

responses and fallbacks remain grounded and localized;

all required tests pass; and

the graph remains Planner -> Execute -> Response -> END.

23. Deferred Next Milestones

Customer notifications for confirmation, payment status, dispatch, delivery, andcancellation.

OTP-based customer authentication and verified phone ownership.

Authenticated staff fulfilment APIs.

Production payment provider adapter, initially Razorpay when merchant setup exists.

Production privacy, security hardening, rate limiting, observability, deployment,backup, and disaster recovery.
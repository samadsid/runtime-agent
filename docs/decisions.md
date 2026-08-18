# Architecture Decisions

## ADR-020

Use typed deferred intent and deterministic customer-entry routing for category-led shopping.

Status

Accepted

Reason

A stable first-time customer must complete profile review before customer-specific
commerce mutations without losing a clear initial request. The execution boundary
therefore redirects a validated planner command to onboarding and checkpoints only a
bounded intent projection. After profile persistence it resumes through the existing
capability/service path using the original trusted request identity. This preserves
the frozen Planner → Execute → Response graph, keeps capabilities independent, and
makes direct-cart continuation idempotent under webhook replay and checkpoint races.

Returning greetings and broad discovery load authoritative categories by default;
stronger product, cart, checkout, and order intents retain their existing routes.

---

## ADR-019

Use one typed semantic React Native design system for the staff application.

Status

Accepted

Reason

The staff application must support system light/dark appearance, compact through
expanded layouts, large fonts, and accessible operational states without duplicating
raw presentation values across feature routes. React Native `StyleSheet` styles,
semantic theme tokens, live `useWindowDimensions()` tiers, safe-area primitives, and
one internal icon wrapper keep presentation portable and separate from staff API and
commerce business behavior. Expo Router route identity, TanStack Query ownership,
authorization, optimistic versions, and idempotency remain outside the theme layer.

NativeWind, browser CSS, large component frameworks, and separate phone/tablet route
trees are excluded.

---

## ADR-017

Use `ProductStatus` as the single mutable catalog lifecycle value and expose legacy
`available` only as a derived domain property.

Status

Accepted

Reason

Catalog administration requires an explicit lifecycle without two independently
mutable availability fields.

---

## ADR-018

Record every physical and reservation inventory effect in one append-only ledger.

Status

Accepted

Reason

Balance changes and movements must share the existing transaction so stock remains
reconcilable without a competing reservation implementation.

---

## ADR-001

Use LangGraph as the orchestration engine.

Status

Accepted

---

## ADR-002

Keep LangChain behind adapters.

Status

Accepted

Reason

Prevent framework leakage.

---

## ADR-003

Capabilities are NOT graph nodes.

Status

Accepted

Reason

Adding a capability should not require modifying the graph.

---

## ADR-004

Conversation history is stored using LangGraph checkpoints.

Status

Accepted

Reason

Avoid custom memory implementations.

---

## ADR-005

Planner decides.

CommandHandler executes.

Status

Accepted

---

## ADR-006

Conversation history and business state are different.

Status

Accepted

Reason

Messages describe conversation.

Session describes commerce.

---

## ADR-007

Do not introduce duplicate Product models.

Status

Accepted

Reason

Current Product model is lightweight enough.

---

## ADR-008

Do not introduce SessionUpdate.

Status

Accepted

Reason

Store the current session instead of patches.

---

## ADR-009

Prompt Builder should receive domain models.

Status

Accepted

Planner receives

- messages
- session

Never pass CommerceGraphState directly.

---

## ADR-010

Use explicit checkpoint serialization boundaries.

Status

Accepted

Reason

Planner responses are transient node-to-node values and use LangGraph's
untracked channel. Durable commerce models are explicitly allowlisted in the
LangGraph MsgPack serializer at the graph-memory adapter boundary.

---

## ADR-011

Resolve product ordinals against typed commerce session state.

Status

Accepted

Reason

The planner may identify a requested 1-based ordinal, but product identity is
resolved deterministically by the selection capability against the most recent
ordered product results stored in `CommerceSession`.

Revisit before production persistence.

---

## ADR-012

Generate customer responses from typed, approved execution outcomes.

Status

Accepted

Reason

Capabilities and domain services remain authoritative for execution status,
approved facts, missing information, and allowed options. A presentation-only
`ResponseNode` uses an LLM to express that approved outcome in the customer's
language and references every approved fragment and question ID. The outcome
is transient and is not checkpointed.

The latest customer message may be passed separately as a language signal.
No language list or translated application copy is hardcoded. The response
prompt requires the LLM to preserve approved business values exactly and to
avoid adding facts or outcomes.

---

## ADR-013

Keep the cart in immutable commerce session state for the in-memory slice.

Status

Superseded by ADR-014

Reason

Cart items are ordered `CartItem` values stored in `CommerceSession`. Product
identity is resolved by `Product.id`; adding the same product replaces its
quantity without changing its cart ordinal. Cart ordinals and recent
product-result ordinals are separate namespaces. Cart mutation rules remain in
the commerce domain, while capabilities validate inputs and produce approved
execution outcomes.

Revisit when cart state must survive process restarts or support concurrent
updates.

---

## ADR-014

Persist active carts in PostgreSQL and keep a checkpointed session snapshot.

Status

Accepted

Reason

The database cart must survive restarts and serialize concurrent mutations.
`CommerceSession.cart_items` remains useful planner context, but capabilities
refresh it from the repository and never treat it as authoritative.

---

## ADR-015

Select the LangGraph checkpointer through application configuration.

Status

Accepted

Reason

Local development may use process-local memory. Production uses LangGraph's
PostgreSQL checkpointer and its schema lifecycle; no custom short-term memory
tables are introduced.

---

## ADR-016

Inject tenant identity from trusted server configuration.

Status

Accepted

Reason

Cart persistence requires a tenant boundary before authentication exists.
Keeping tenant selection out of the public chat request avoids trusting an
unauthenticated caller and leaves authentication as a later boundary change.

---

## ADR-017

Keep checkout state in the commerce session and confirmed orders in PostgreSQL.

Status

Accepted

Reason

Checkout details are incomplete conversational workflow state and must resume
through LangGraph checkpoints. An order exists only after explicit confirmation
and is durable commerce data with immutable item snapshots.

---

## ADR-018

Use the source cart as the order-confirmation idempotency key.

Status

Accepted

Reason

A unique order-to-cart link makes retries and concurrent confirmations return
the same order. Cart uniqueness applies only to `ACTIVE` carts so a conversation
can complete more than one cart over time.

---

## ADR-019

Use PostgreSQL balances and reservations as inventory authority.

Status

Accepted

Reason

Cart state does not guarantee stock. Locked inventory balances and durable
per-order reservations prevent concurrent confirmations from overselling and
allow cancellation or delivery effects to be applied idempotently.

---

## ADR-020

Keep fulfilment rules in a domain service and coordinate persistence with a
transaction-scoped unit of work.

Status

Accepted

Reason

Order status, reservations, balances, and audit history must change atomically
without exposing PostgreSQL or framework types to the commerce domain. Staff
HTTP exposure remains deferred until authenticated authorization exists.

---

## ADR-021

Use conversation-scoped customer order access and checkpointed cancellation
intent.

Status

Accepted

Reason

Customer authentication is not available, so every customer order read and
lock includes the trusted conversation ID. Recent-order ordinals and the exact
pending cancellation target are typed checkpoint state, while PostgreSQL
remains authoritative. A customer cancellation requires explicit confirmation
and atomically releases inventory only from `CONFIRMED`.

---

## ADR-022

Use monotonic cart versions and checkpointed clear intent.

Status

Accepted

Reason

Quantity updates and complete-cart clearing mutate the authoritative PostgreSQL
cart without adding graph nodes. Every effective item mutation increments the
cart version. A clear request checkpoints the trusted tenant-scoped cart ID and
reviewed version, and confirmation locks and compares that version before
deleting items. This prevents stale or repeated conversational confirmation
from clearing a newer cart while keeping short-term intent out of business
tables.

---

## ADR-023

Use typed stock-conflict results and checkpointed recovery choices.

Status

Accepted

Reason

Expected inventory shortages are normal commerce outcomes, not application
exceptions. Final confirmation locks the exact reviewed cart version and all
required inventory rows before writing an order. Customer recovery choices are
typed, ordinal-scoped interaction state; every recovery mutation rechecks
PostgreSQL and cannot exceed the quantity previously offered.

---

## ADR-024

Resolve saved delivery details from transient trusted channel context and keep
PostgreSQL authoritative.

Status

Accepted

Reason

Saved details are a convenience feature, not authentication. Tenant, channel,
and channel customer identity are injected outside LLM arguments and are not
checkpointed. PostgreSQL owns profiles, addresses, optimistic versions, and
default uniqueness; checkpoint state contains only safe ordinal projections and
minimal pending consent/use workflows. Checkout and orders receive copied value
snapshots so later saved-address mutations cannot change a pending or historical
order.

Checkout may proactively retrieve the default saved details through the saved-
delivery service and present them as one pending offer. The offer keeps the phone
masked and remains non-authoritative until explicit acceptance reloads and checks
the saved profile and address before copying their values into checkout.

---

## ADR-025

Use provisional orders and a provider-neutral port for online payments.

Status

Accepted

Reason

Reservations and immutable commercial snapshots must exist before leaving for
hosted payment, while external calls must not hold database transactions open.
The source cart creates one provisional order and local attempt transactionally;
provider creation is persisted in a second transaction. Only verified,
idempotent events can confirm the order. Provider adapters and reconciliation
remain outside LangGraph, and COD continues through its existing confirmation
transaction.

---

## ADR-026

Use a durable inbox/outbox channel adapter for Twilio WhatsApp.

Status

Accepted

Reason

Signed webhooks must acknowledge independently of LLM latency, provider retries
must not rerun commerce decisions, and a transport sender is trusted only as a
channel identifier. PostgreSQL owns channel mappings, delivery records,
ordering, leases, and callback idempotency; LangGraph continues to own short-term
conversation state. Trusted request and channel identity remain transient graph
input and never become planner arguments.

---

## ADR-027

Use a thin browser channel with durable REST request receipts.

Status

Accepted

Reason

The browser must render only the approved backend reply and keep its transcript
as non-authoritative presentation state. A stable optional request UUID lets a
manual retry return a completed response without rerunning the graph. Requests
that began execution but did not persist a response remain ambiguous rather
than risking duplicate commerce effects. PostgreSQL advisory locks serialize
REST and external-channel work for the same conversation without changing the
graph, planner, or capabilities.

---

## ADR-028

Hydrate a safe customer-profile projection before planning and complete onboarding
through the existing saved-delivery aggregate.

Status

Accepted

Reason

Returning-customer recognition needs a trusted durable lookup while raw phone and
address values must stay out of ordinary prompts. Checkpoint state owns the
uncommitted proposal; explicit confirmation performs one atomic profile, address,
consent, and idempotency write without changing the frozen graph.

---

## ADR-029

Resolve direct product-and-quantity cart intent through deterministic commerce
policies and an isolated pending ordinal namespace.

Status

Accepted

Reason

The planner extracts only the customer-supplied product query, quantity, and
optional unit. Tenant-scoped catalog resolution auto-selects only an exact
normalized name or a sole candidate; ambiguity is checkpointed without cart
mutation. The repository atomically revalidates the product, applies existing
add-or-replace semantics, and records the trusted request receipt without
changing the frozen graph or allowing capabilities to call one another.

---

## ADR-030

Browse the authoritative catalog through a deterministic service and a single
checkpointed page projection.

Status

Accepted

Reason

General assortment requests must not become fabricated product searches. A
framework-independent catalog browse service owns small-versus-large catalog
policy, bounded offset pagination, category resolution, and stable ordering.
PostgreSQL owns catalog facts while `CommerceSession.catalog_browse` retains
only the latest displayed page for isolated ordinal resolution. Follow-up
navigation and selection reload tenant-scoped data, and successful product
selection clears browse state. This adds capabilities without changing the
frozen graph or coupling capabilities to one another.

---

## ADR-031

Use a transactional notification outbox and deterministic proactive templates.

Status

Accepted

Reason

Every customer-visible order transition must commit its notification intent with
the authoritative status and history row, while provider availability must remain
outside commerce transactions. A notification outbox owns business intent and a
separate channel outbox owns provider delivery. Reviewed versioned templates replace
LLM generation for proactive messages; leased workers, idempotent delivery links,
and reconciliation make retries harmless without changing the frozen graph.

---

## ADR-032

Expose staff fulfilment through a separate authenticated, tenant-scoped HTTP path.

Status

Accepted

Reason

Staff operations are deterministic administrative commands and must not be
authorized or interpreted by the customer planner or an LLM. Short-lived
asymmetrically signed tokens establish staff identity, while current PostgreSQL
account and membership records establish the tenant and role on every request.
Order versions prevent stale writes, and a transaction-scoped idempotency receipt
makes retries commit with the existing inventory, history, and notification effects.

---

## ADR-033

Use one Expo mobile adapter for staff and administrator fulfilment operations.

Status

Accepted

Reason

Both roles operate the same tenant-scoped staff API, while the backend remains
authoritative for identity, permissions, permitted actions, transitions, inventory,
audit history, and notification intent. SecureStore owns only the short-lived access
token, TanStack Query owns memory-only server projections, and one retained client
idempotency key represents each unresolved logical status action. The mobile adapter
does not invoke or modify the customer graph.

---

## ADR-034

Select one persisted WhatsApp delivery provider through application composition.

Status

Accepted

Reason

Twilio and Meta Cloud API share the same customer channel, durable conversation
mapping, inbox/outbox workers, notification intent, and runtime idempotency
boundaries. Persisting the provider on message and delivery records keeps retries
and callbacks routed to the adapter that owns their external identifiers, while a
single startup selector prevents both transports from accepting new traffic.
Provider-specific signatures, credentials, payloads, and errors remain outside
commerce and LangGraph. A cutover leaves WhatsApp workers not-ready until unresolved
old-provider work is explicitly drained or dispositioned.

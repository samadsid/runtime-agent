# Current Status

## Completed

### WhatsApp Delivery Location and Serviceability

- Signed Meta location attachments normalize to bounded provider-neutral Decimal
  coordinates and remain bound to the claimed inbound message
- Planner and response prompts receive coordinate-free facts; capabilities never
  accept generated coordinates
- Active tenant-owned PostGIS MultiPolygons decide coverage with boundary-inclusive,
  priority-stable lookup
- Location-aware onboarding, explicit save consent, saved-address revalidation, and
  atomic COD/online confirmation checks preserve carts on stale zones or failures
- ADMIN staff APIs and the responsive mobile map editor manage, preview, test,
  activate, and deactivate versioned coverage boundaries
- Forward and reverse geocoding ports are present with disabled adapters; ambiguous
  or unavailable text geocoding fails closed and requests an exact pin

The graph remains `START → PlannerNode → ExecuteNode → ResponseNode → END`.

### Checkout Conversation UX and Public Order Numbers

- COD-only checkout auto-selects and discloses COD; multiple operational methods use
  an explicit checkpointed payment-selection stage and confirmation-time revalidation
- Final reviews contain deterministic item lines, totals, masked contact details,
  delivery address, payment method, and one final action
- Response composition and fallback understand WhatsApp-safe sections, lists, totals,
  and protected business values
- Newly onboarded, returning-after-inactivity, and continuing customer entries are
  distinguished by trusted runtime state
- Orders have immutable tenant-scoped public numbers used by customer, notification,
  and staff projections while UUIDs remain internal relationship identities

The graph remains `START → PlannerNode → ExecuteNode → ResponseNode → END`.

### Category-Led Customer Shopping Journey

- Stable first-time customer requests are redirected to combined profile onboarding
  before customer-specific commerce mutations without discarding a supported intent
- Typed, TTL-bounded deferred browse, search, direct-add, cart, and order projections
  are checkpointed with trusted request identity and resumed after confirmation
- Successful onboarding without a stronger intent and returning-customer greetings
  show the current authoritative category page
- Broad discovery is category-first while explicit product, cart, checkout, and order
  intents retain direct routing
- Customer-visible, active, non-empty category eligibility is tenant-scoped and
  deterministic; changed categories refresh current choices safely
- Deferred direct additions reuse existing cart idempotency and catalog/stock
  revalidation, preventing duplicate mutations during retry or webhook replay

The graph remains `START → PlannerNode → ExecuteNode → ResponseNode → END`.

### React Native Staff Design System and Responsive UI

- Typed MeatUncle semantic light/dark themes following system appearance
- Semantic typography, spacing, radii, elevation, motion, and responsive breakpoint
  tokens with compact, medium, and expanded layout utilities
- Shared accessible text, icon, button, field, card, badge, chip, metric, feedback,
  loading, confirmation, and responsive composition components
- Compact bottom navigation and medium/expanded role-filtered navigation rail
- Responsive redesign of session restoration, login, account, dashboard, orders,
  catalog/product administration, and inventory/movement workflows
- Centralized order, product-lifecycle, and stock-state presentation adapters
- Virtualized order, catalog, and inventory-movement lists plus standardized initial,
  refresh, empty, filtered-empty, error, offline, stale, disabled, and mutation states
- Development-only synthetic component gallery and static UI boundary audit
- Rotation/tablet configuration, Expo font/asset integration, responsive boundary
  tests, accessibility component assertions, typecheck, and Expo Doctor verification

The redesign does not change staff API contracts, backend authorization, commerce
rules, optimistic versions, or mutation idempotency. Theme and responsive state are
presentation-only; query cache and form/business state remain with their existing
owners.

### Catalog and Inventory Administration

- ADMIN-only tenant-scoped product creation, editing, activation, and deactivation
- Independent optimistic product and inventory versions with staff idempotency
- Atomic physical-stock adjustments and immutable inventory movements
- Order reservation, release, and consumption ledger integration
- Low/out-of-stock queries and summaries plus detection-only reconciliation
- Role-aware React Native Catalog and Inventory workflows

The deterministic staff path remains separate from the customer graph. Product status
is the canonical lifecycle value; customer availability is derived from active status,
visibility policy, and positive sellable inventory.

### Runtime

- FastAPI
- CommerceRuntime
- CommerceGraph

The authenticated staff fulfilment API is available separately under
`/api/staff/v1`. It uses Argon2id credentials, short-lived asymmetric JWTs,
database-backed account/membership authorization, tenant-scoped order queries,
cursor pagination, optimistic order versions, and transactional idempotent status
updates. It does not enter the customer runtime or graph.

---

### Graph

- PlannerNode
- ExecuteNode
- ResponseNode

The graph flow is `START → PlannerNode → ExecuteNode → ResponseNode → END`.

Execution outcomes are typed and transient. Response generation emits exactly
one assistant message from approved fragments and follow-up questions, with a
deterministic fallback when LLM composition fails validation.

Responses use the LLM to match any language, script, and chat style present in
the latest customer message, without hardcoded language detection or copies.

---

### Planner

- Structured output
- PlannerDecision
- PlannerCommand mapping

---

### Capabilities

Implemented

- Greeting
- Search Product
- Select Product by ordinal reference
- Add selected product to cart
- Add one uniquely resolved catalog product and quantity directly to the cart,
  with checkpointed clarification for ambiguous matches
- View ordered cart items
- Remove cart item by cart ordinal
- Update a persisted cart item's quantity by cart ordinal or an exact unique
  structured cart-product reference
- Review and explicitly confirm clearing the exact persisted cart version
- Checkout review and delivery-detail collection
- Checkout delivery-detail correction with checkpointed two-turn replacement
  collection and a fresh confirmation review
- Idempotent checkout abandonment that preserves the persisted active cart
- Explicit cash-on-delivery order confirmation
- Stock-aware, all-or-nothing confirmation with typed multi-item shortages
- Explicit recovery by accepting a revalidated available quantity
- Latest order-status lookup
- Inventory reservation during confirmed order creation
- Domain-controlled fulfilment transitions, cancellation release, delivery
  consumption, and status audit history
- Conversation-scoped recent order history and customer-safe order details
- Two-step customer cancellation restricted to `CONFIRMED` orders
- Trusted-channel saved delivery profiles with optional name and unverified phone
- Multiple saved addresses with list/select/add/update/delete/default operations
- Explicit save consent and typed second-turn overwrite/profile-use confirmation
- Dedicated saved-address ordinals and checkout value snapshots
- Proactive default saved-detail offers at checkout with masked phone display and
  explicit acceptance before copying values into checkout
- Explicit COD or online payment-method selection
- First-visit trusted-channel onboarding with combined detail collection,
  checkpointed review, explicit consent, and atomic saved-profile completion
- Provider-neutral online checkout with provisional orders and reservations
- Durable fake-provider checkout, signed webhook simulation, and payment status
- Idempotent payment retry, expiry/failure release, COD switching, and reconciliation
- Authoritative catalog browsing for small and large catalogs, including category
  resolution, bounded product/category pages, next/previous navigation, isolated
  browse ordinals, expiry, cancellation, and revalidated product selection

The active cart is stored in PostgreSQL through a commerce-domain repository.
`CommerceSession` carries a checkpointed snapshot refreshed by cart reads and
mutations. Re-adding the same product replaces its quantity at the existing
cart position. Product-result ordinals and cart ordinals remain separate.
Active carts have a monotonic version incremented by effective item mutations.
Clear-cart confirmation stores the reviewed cart ID and version in checkpointed
session state, rejects stale confirmation, and leaves the active cart record
available after its items are cleared. Every effective cart mutation invalidates
in-progress checkout state. A successful product add immediately establishes a
new version-bound cart review and includes it in the add response, so a following
checkout request advances to delivery details without repeating the review.

Checkout workflow state is checkpointed in `CommerceSession`. Confirmed orders
and item snapshots are stored in PostgreSQL, with cart closure and order creation
committed atomically and idempotently by source cart.

Customers may correct one or more delivery details while checkout is collecting
or reviewing them. A typed pending correction field gives the next bare message
an exact delivery-field meaning, and every accepted correction requires a new
explicit order confirmation. Abandoning checkout resets only this short-lived
checkout state; it does not clear the active cart or touch orders or inventory.

Confirmation also locks product-level balances and creates active inventory
reservations in that transaction. Product search excludes products without
positive sellable inventory. The fulfilment service and PostgreSQL unit of work are
exposed through the authenticated staff API with authorization, actor derivation,
optimistic versions, idempotency, and safe request correlation.

Confirmation now requires the exact checkpointed cart version reviewed by the
customer. It returns typed confirmed, stock-unavailable, or stale-checkout
results; the shortage path writes no order, reservation, inventory, or cart
state. Typed checkpoint recovery choices keep recovery ordinals separate from
cart ordinals. Accepting a displayed available amount re-locks the cart and
inventory, caps the update at the offered quantity, increments the cart version,
and requires checkout review again. Deadlock and serialization failures use a
confirmation-scoped three-attempt retry policy before a safe temporary failure.

Recent customer order results and a structured pending cancellation target are
checkpointed in `CommerceSession`. Order references are resolved by durable
UUID, recent-order ordinal, or latest order, and are re-authorized through
conversation-scoped repository queries. Customer cancellation releases active
reservations and writes a `CUSTOMER` audit entry in the existing fulfilment
transaction.

---

### Memory

Completed

- Configurable LangGraph MemorySaver for local development
- LangGraph PostgreSQL checkpointer for production
- Conversation restoration
- Thread ID support

Conversation ID remains the LangGraph thread ID. PostgreSQL checkpointer setup
is owned by application infrastructure lifecycle.

Typed commerce session state is checkpointed independently of the generic
message-only conversation contract.

The current catalog browse page is checkpointed as a typed projection with a
configured TTL. It contains only customer-safe category or product options;
PostgreSQL remains authoritative and every navigation or selection reload is
tenant scoped. Browse category, browse product, search product, pending direct
add, cart, order, recovery, and saved-address ordinals remain separate.

Trusted channel context is transient and excluded from checkpoint state. Saved
address projections and minimal pending confirmation workflows are checkpointed;
durable profiles and addresses remain PostgreSQL-authoritative.

Onboarding proposals remain checkpointed only until confirmation or skip. Returning
customers are recognized through a pre-planner safe projection that excludes durable
phone numbers and addresses.

---

### Message Adapter

Completed

Domain Messages

↔

LangChain Messages

---

### Customer Order Notifications

Completed

- Atomic notification intent for confirmed, preparing, out-for-delivery, delivered,
  and cancelled order transitions
- Tenant-scoped notification outbox with leased processing, retries, suppression,
  dead letters, and reconciliation
- Reviewed English, Hindi, and Roman-script Hinglish templates without LLM use
- Free-form WhatsApp delivery inside the service window and approved Twilio Content
  Templates outside it
- Separate notification and provider-delivery lifecycle records
- Payment notification contracts are defined but production emission remains disabled

### Twilio WhatsApp Sandbox Channel

Completed

- Exact-URL signature validation for inbound and status webhooks
- Durable conversation mapping, inbox, outbox, and delivery events
- Asynchronous ordered processing and persist-before-send delivery
- Trusted channel/request context outside planner arguments
- Bounded retries, dead letters, ambiguous sends, monotonic callbacks, and
  customer-service-window enforcement
- Text-only unsupported-media handling
- Liveness, readiness, and Prometheus metrics

The REST channel and frozen graph remain unchanged.

### Meta WhatsApp Cloud API Channel

Completed

- `disabled`, `twilio`, or `meta_cloud` selection at the composition root
- Provider-neutral WhatsApp identity with collision-checked Twilio backfill
- Meta verification challenge and raw-body App Secret HMAC validation
- Bounded text/unsupported-message and delivery-status webhook normalization
- Atomic batch inbox/status persistence with provider-scoped `wamid` deduplication
- Pooled Graph API text/template delivery with typed permanent, retryable, and
  ambiguous outcomes
- Persisted approved-template metadata, service-window enforcement, monotonic
  sent/delivered/read projection, orphan callbacks, and immutable event history
- Safe cutover blocking, provider-aware readiness, secret-safe metrics, and Meta
  adapter/webhook tests

Graph API `v25.0` is the deployment default. Operators must confirm it remains
supported for the configured Meta app and review it no later than 2027-11-18.
The test-number setup, verified recipient, long-lived production token, approved
business templates, and public HTTPS endpoint remain deployment-owned.

---

### Customer Web Chat

Completed

- Responsive React and strict TypeScript chat interface
- Safe Unicode and multiline reply rendering
- Local transcript and conversation continuity
- Manual retry with stable request identifiers
- Durable REST request receipts and per-conversation serialization
- Explicit development and production CORS origins
- Keyboard, screen-reader, and 320-pixel responsive behavior
- Unit, component, API-contract, and browser smoke tests

The browser remains a presentation-only channel adapter. Commerce behavior and
the frozen graph remain unchanged.

---

### Staff Mobile Dashboard

Implemented

- Android-first Expo and strict TypeScript application in `staff-mobile/`
- SecureStore access-token lifecycle with cold-start `/me` validation
- Role-aware dashboard, cursor-paginated order queue, and protected order details
- Server-provided fulfilment actions, admin cancellation, optimistic versions, and
  retained logical idempotency keys for ambiguous retries
- In-memory-only customer PII, coordinated session expiry, and complete logout cleanup
- Runtime-validated API contracts, accessible light/dark design primitives, and offline,
  loading, empty, error, and conflict states
- Unit, component, API-client, and Maestro acceptance coverage
- Development, staging preview APK, and production AAB build profiles

The staff REST API now exposes explicit mobile-safe order DTOs, active membership,
typed permitted actions, and a tenant-scoped dashboard summary. Signing a preview APK
and physical-device/staging execution require deployment-owned EAS credentials, seeded
staff accounts, and a reachable HTTPS staging backend.

---

## Future

- Multi-tenant support
- Streaming
- Human-in-the-loop
- Observability

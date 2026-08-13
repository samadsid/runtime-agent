# Current Status

## Completed

### Runtime

- FastAPI
- CommerceRuntime
- CommerceGraph

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
- Explicit COD or online payment-method selection
- First-visit trusted-channel onboarding with combined detail collection,
  checkpointed review, explicit consent, and atomic saved-profile completion
- Provider-neutral online checkout with provisional orders and reservations
- Durable fake-provider checkout, signed webhook simulation, and payment status
- Idempotent payment retry, expiry/failure release, COD switching, and reconciliation

The active cart is stored in PostgreSQL through a commerce-domain repository.
`CommerceSession` carries a checkpointed snapshot refreshed by cart reads and
mutations. Re-adding the same product replaces its quantity at the existing
cart position. Product-result ordinals and cart ordinals remain separate.
Active carts have a monotonic version incremented by effective item mutations.
Clear-cart confirmation stores the reviewed cart ID and version in checkpointed
session state, rejects stale confirmation, and leaves the active cart record
available after its items are cleared. Every effective cart mutation invalidates
in-progress checkout state.

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
positive sellable inventory. The fulfilment service and PostgreSQL unit of work
are implemented for staff-side status changes; HTTP exposure remains deferred
until staff authentication, authorization, actor derivation, and request
correlation are available.

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

## Future

- Authentication
- Authenticated staff fulfilment status API
- Multi-tenant support
- Streaming
- Human-in-the-loop
- Observability

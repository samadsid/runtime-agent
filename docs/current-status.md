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
- View ordered cart items
- Remove cart item by cart ordinal
- Update a persisted cart item's quantity by cart ordinal or an exact unique
  structured cart-product reference
- Review and explicitly confirm clearing the exact persisted cart version
- Checkout review and delivery-detail collection
- Explicit cash-on-delivery order confirmation
- Latest order-status lookup
- Inventory reservation during confirmed order creation
- Domain-controlled fulfilment transitions, cancellation release, delivery
  consumption, and status audit history
- Conversation-scoped recent order history and customer-safe order details
- Two-step customer cancellation restricted to `CONFIRMED` orders

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

Confirmation also locks product-level balances and creates active inventory
reservations in that transaction. Product search excludes products without
positive sellable inventory. The fulfilment service and PostgreSQL unit of work
are implemented for staff-side status changes; HTTP exposure remains deferred
until staff authentication, authorization, actor derivation, and request
correlation are available.

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

---

### Message Adapter

Completed

Domain Messages

↔

LangChain Messages

---


## Future

- Authentication
- Authenticated staff fulfilment status API
- Multi-tenant support
- Streaming
- Human-in-the-loop
- Observability

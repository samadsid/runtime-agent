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
- Checkout review and delivery-detail collection
- Explicit cash-on-delivery order confirmation
- Latest order-status lookup

The active cart is stored in PostgreSQL through a commerce-domain repository.
`CommerceSession` carries a checkpointed snapshot refreshed by cart reads and
mutations. Re-adding the same product replaces its quantity at the existing
cart position. Product-result ordinals and cart ordinals remain separate.

Checkout workflow state is checkpointed in `CommerceSession`. Confirmed orders
and item snapshots are stored in PostgreSQL, with cart closure and order creation
committed atomically and idempotently by source cart.

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
- Multi-tenant support
- Streaming
- Human-in-the-loop
- Observability

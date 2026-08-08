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

The cart is stored as immutable, session-scoped in-memory state. Re-adding the
same product replaces its quantity at the existing cart position. Product
result ordinals and cart ordinals are separate namespaces.

---

### Memory

Completed

- LangGraph MemorySaver
- Conversation restoration
- Thread ID support

Verified working.

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

- Checkout capability
- PostgreSQL checkpointing
- Authentication
- Multi-tenant support
- Streaming
- Human-in-the-loop
- Observability

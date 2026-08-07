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

- Cart capability
- Checkout capability
- PostgreSQL checkpointing
- Authentication
- Multi-tenant support
- Streaming
- Human-in-the-loop
- Observability

# Architecture

## High Level

```
FastAPI

↓

CommerceRuntime

↓

CommerceGraph (LangGraph)

↓

PlannerNode

↓

ExecuteNode

↓

CommandHandler

↓

Capabilities

↓

ResponseNode
```

---

## Layers

### API

Responsible for HTTP only.

No business logic.

---

### Runtime

Responsible for orchestrating the graph.

No business rules.

---

### Graph

Responsible for workflow.

No commerce logic.

---

### Planner

Responsible for deciding the next action.

Never executes business logic.

---

### CommandHandler

Executes planner commands.

---

### Response Generation

`ExecuteNode` stores a typed execution outcome in transient graph state.

`ResponseNode` turns that outcome into one assistant message. It may only
arrange approved response fragments and follow-up questions; it does not make
business decisions, execute capabilities, or modify `CommerceSession`.

Customer-visible text is generated from approved outcome data. The response
LLM receives the latest customer message only as a language, script, tone, and
chat-style signal, so it can respond naturally in any language the model
supports. It must preserve approved names, prices, quantities, units,
availability, and option numbers exactly. No other conversation or session
data crosses the response prompt boundary.

---

### Capabilities

Business logic lives here.

Capabilities are independent modules.

Examples

- Greeting
- Search Product
- Add To Cart
- Checkout

---

# Message Flow

```
User

↓

ConversationState

↓

MessageAdapter

↓

LangChain Messages

↓

Planner

↓

Command

↓

Capability

↓

Typed Execution Outcome

↓

ResponseNode

↓

Assistant Message
```

---

# State

Conversation History

- LangGraph Messages

Business State

- CommerceSession

`CommerceSession` owns selected-product context and an ordered snapshot of the
active cart. PostgreSQL is authoritative for carts; cart capabilities refresh
the snapshot after every persisted read or mutation. The snapshot is restored
with the session through LangGraph checkpoints for planning context.

`CommerceSession.checkout` is short-term workflow state. It records the
reviewed source cart, collection stage, and delivery details until a customer
explicitly confirms. It is checkpointed but is never an order.

Confirmed orders and immutable order-item snapshots are authoritative in
PostgreSQL. Order creation and cart closure occur in one repository transaction;
the source cart uniquely identifies an idempotent confirmation.

`CommerceSession` is commerce-specific typed state owned by
`CommerceGraphState`. It is restored by LangGraph checkpoints using the
conversation thread ID and does not cross the generic, message-only
`ConversationState` boundary.

Planner responses and execution outcomes are transient graph data and are not
checkpointed.

Tenant and conversation identity enter capability execution through a typed
runtime context. The HTTP client does not select a tenant; the application
injects its configured tenant until authentication is introduced.

These are intentionally separate.

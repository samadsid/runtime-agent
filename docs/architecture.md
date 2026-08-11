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
reviewed source cart and exact cart version, collection stage, delivery details,
and any current stock-recovery choices until the workflow is reset. It is
checkpointed but is never an order or authoritative inventory state.

`CommerceSession.recent_order_results` is the ordered source for customer order
ordinals. `CommerceSession.pending_order_cancellation` stores the exact durable
order ID awaiting explicit confirmation. Both values are checkpointed
interaction state; PostgreSQL orders and reservations remain authoritative.

`CommerceSession.pending_cart_clear` stores the active cart ID and monotonic
version shown during a clear-cart review. It is checkpointed interaction state,
not a business record. PostgreSQL remains authoritative for cart items, and a
confirmation can clear only the exact reviewed cart version.

Confirmed orders and immutable order-item snapshots are authoritative in
PostgreSQL. Order creation and cart closure occur in one repository transaction;
the source cart uniquely identifies an idempotent confirmation.

Product inventory balances and order reservations are also authoritative in
PostgreSQL. Confirmation locks balances and creates reservations in the same
transaction as the order and cart closure. A framework-independent fulfilment
service controls order transitions; its PostgreSQL unit of work applies status,
reservation, balance, and audit-history changes atomically. Staff fulfilment
does not pass through the customer planner or graph.

Final confirmation passes trusted tenant/conversation identity plus the exact
reviewed cart ID and version into the commerce service. The PostgreSQL
transaction returns typed confirmation, shortage, or stale-checkout results.
Shortages create no durable writes. A customer may explicitly accept a
previously offered available quantity through a cart mutation that locks and
rechecks both the reviewed cart version and current inventory; every successful
recovery mutation invalidates checkout and requires a new review.
Customer order reads are always scoped by `conversation_id`. Customer
cancellation uses the fulfilment unit of work but applies the stricter policy
that only `CONFIRMED` orders may be cancelled.

`CommerceSession` is commerce-specific typed state owned by
`CommerceGraphState`. It is restored by LangGraph checkpoints using the
conversation thread ID and does not cross the generic, message-only
`ConversationState` boundary.

Planner responses and execution outcomes are transient graph data and are not
checkpointed.

Tenant and conversation identity enter capability execution through a typed
runtime context. The HTTP client does not select a tenant; the application
injects its configured tenant until authentication is introduced.

Trusted channel identity also enters through that application-owned context and
is transient graph input. It is never accepted through planner arguments or
stored in checkpoints. The REST adapter supports an explicitly enabled
development-only customer header; omission is guest mode.

Saved delivery profiles and addresses are authoritative in PostgreSQL.
`CommerceSession.recent_saved_addresses` is a short-lived, ordered projection
for a dedicated ordinal namespace. Pending saved-detail offers and confirmations
are typed checkpointed workflow state, while selected delivery values are copied
into checkout as snapshots. Saved-address changes never alter an existing
checkout review or immutable order snapshot.

These are intentionally separate.

## External Conversational Channels

Twilio WhatsApp is an infrastructure adapter around `CommerceRuntime`; it does
not add graph nodes or enter capability models. Signed webhooks persist into a
PostgreSQL inbox, background workers invoke the unchanged graph with transient
trusted channel context, and the exact approved response is committed to an
outbox before provider delivery. PostgreSQL channel mappings provide stable UUID
conversation IDs while LangGraph remains authoritative for conversation state.

Inbox leases, oldest-message selection, and tenant/conversation advisory locks
serialize one graph thread while permitting different conversations to run in
parallel. Outbound delivery and monotonic callbacks are independent of agent
execution, so provider retries never regenerate a response.

The customer web frontend is another outer channel adapter. It retains only a
local presentation transcript and the backend-issued conversation UUID, then
submits text through the existing REST runtime boundary. PostgreSQL request
receipts deduplicate browser retries, and an infrastructure advisory lock
serializes calls to one graph thread. The frontend never owns commerce state or
interprets internal outcomes.

## Online Payments

Online payments preserve the existing graph. Payment capabilities call a
framework-independent payment service, which depends on a provider port;
provider adapters, webhook HTTP handling, and PostgreSQL implementations remain
at infrastructure boundaries.

An online confirmation atomically creates an `AWAITING_PAYMENT` order, immutable
item snapshots, active reservations, and a local `CREATING` attempt before any
provider call. Verified provider events are the only path to `CONFIRMED`.
PostgreSQL owns orders, attempts, webhook idempotency, reservations, and fake
provider records. A lifespan reconciliation loop uses bounded `SKIP LOCKED`
claims and the same event transition service as webhooks.

# Architecture Decisions

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

Accepted

Reason

Cart items are ordered `CartItem` values stored in `CommerceSession`. Product
identity is resolved by `Product.id`; adding the same product replaces its
quantity without changing its cart ordinal. Cart ordinals and recent
product-result ordinals are separate namespaces. Cart mutation rules remain in
the commerce domain, while capabilities validate inputs and produce approved
execution outcomes.

Revisit when cart state must survive process restarts or support concurrent
updates.

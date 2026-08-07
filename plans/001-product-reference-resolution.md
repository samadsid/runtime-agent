# Product Reference Resolution Implementation Plan

## Root cause

Product search returned typed products from the capability, but the handler
discarded everything except the rendered assistant message. The graph had no
commerce session, and the planner received only message text, so a later phrase
such as “first one” could only be interpreted by rereading that text. There was
also no deliberate selection capability, causing the planner to substitute a
new search using an inferred product name.

`PlannerResponse` was a normal checkpoint channel, which caused LangGraph's
MsgPack serializer to warn when restoring its unregistered Pydantic type.

## Design and reasoning

Add an immutable `CommerceSession` containing the latest ordered product
results and an optional selected product. Keep it exclusively in
`CommerceGraphState`; `ConversationState` remains an unchanged generic,
message-only runtime contract.

An incoming graph state has `session=None`. A LangGraph reducer retains the
checkpointed session when the incoming value is `None`, while accepting every
concrete session produced by execution. This lets a fresh HTTP request restore
commerce state solely by its existing thread ID.

Capabilities and handlers carry their session through generic `SessionT`
transport types, avoiding a commerce dependency in generic runtime contracts.
Search stores its exact ordered results and clears stale selection. A new
`select_product` capability accepts only a strict 1-based integer ordinal and
maps it to the retained tuple. The LLM supplies the ordinal but never supplies
product identity.

## Files and symbols

- `commerce/models/commerce_session.py`: `CommerceSession`.
- `runtime/graph/state.py`: `retain_commerce_session`, session channel, and
  untracked `planner_response`.
- `runtime/graph/memory/checkpointer.py`: exact MsgPack allowlist configuration.
- `runtime/capabilities/{input,output,capability,registry}.py`: generic session
  transport.
- `runtime/handlers/`: session-preserving command and result flow.
- `runtime/capabilities/search_product/capability.py`: retain ordered results.
- `runtime/capabilities/select_product/`: strict ordinal selection capability.
- `runtime/graph/nodes/{planner_node,execute_node}.py`: consume and checkpoint
  commerce session.
- `runtime/planner/planner.py`, `runtime/prompts/planner.py`, prompt renderers,
  and templates: provide typed session context to planning.
- `app/application_container.py`: register and inject the new components.
- Focused tests under `tests/` and status/decision documentation under `docs/`.

`runtime/contracts/state.py`, the conversation-state adapter, API models, graph
topology, and the existing `Product` model remain unchanged.

## Implementation order

1. Add the immutable session model and graph channels.
2. Configure transient planner output and durable session serialization.
3. Thread generic session values through capability and handler contracts.
4. Store product-search results and add deterministic selection.
5. Pass typed session state into planner prompt construction.
6. Register components in the application composition root.
7. Add unit, graph-restoration, and serialization tests.
8. Update architecture decisions and current status.

## Persistence and restoration

LangGraph 1.2.10 supports binary reducers declared through `Annotated`.
`CommerceGraphState.session` uses a reducer that returns the checkpointed value
when fresh input supplies `None`. Execute returns the complete current session,
which LangGraph checkpoints under the conversation's existing `thread_id`.

The installed `JsonPlusSerializer` accepts exact classes through
`allowed_msgpack_modules`. `GraphCheckpointer` supplies
`(CommerceSession, Product)` and passes the serializer to
`MemorySaver(serde=serializer)`. It does not enable global allowlists, JSON
constructor allowlists, or pickle fallback.

## Deterministic ordinal behavior

Product order is the exact order returned by the repository, stored in the
session, and displayed to the customer. `ordinal=1` maps only to tuple index
zero. Missing, non-integer, non-positive, and out-of-range values return
clarification with the unchanged session. No sorting, name matching,
response-text parsing, fallback search, or clamping is allowed.

## PlannerResponse warning

LangGraph 1.2.10 supports
`Annotated[PlannerResponse | None, UntrackedValue]`. The value remains available
to the immediately following execute node but is omitted from checkpoint
values. This removes the warning without coupling planner or domain models to
LangGraph.

## Tests

- Search ordering, replacement, empty results, and selection clearing.
- First and second ordinal selection plus invalid ordinal clarification.
- Message-only second invocation restoring the prior session by thread ID.
- Different thread isolation.
- Planner-to-execute transfer with no checkpointed `PlannerResponse`.
- MsgPack round trip for nested session/product values with no warning.
- Session rendering with stable 1-based labels.
- Existing greeting and direct search flows.

## Risks, assumptions, and deferrals

- The latest completed search is the only referenceable result set; an empty
  newer search invalidates older results.
- Repository order becomes customer-visible selection order.
- The LLM can misclassify an ordinal phrase, but it cannot invent identity for
  the selection capability.
- Untracked planner output cannot resume between planner and execute after a
  process failure; no interruption boundary exists there today.
- `MemorySaver` remains process-local; PostgreSQL checkpointing is deferred.
- Cart, quantities, checkout, pronouns, fuzzy references, older-result
  references, and API exposure of commerce state are deliberately deferred.

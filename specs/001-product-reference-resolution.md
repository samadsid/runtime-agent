Issue: Product Reference Is Resolved Through Conversation Text Instead of Typed Commerce Context

Problem

The agent can search the product catalog and return multiple matching products, but it does not retain those results as structured commerce context.

For example:

The customer says: I want chicken.

The agent searches the catalog and responds with:

Chicken Breast — ₹320.00/kg

Chicken Wings — ₹220.00/kg

The customer says: I want first one.

The planner receives the rendered conversation history and infers that first one means Chicken Breast. It then produces another search_product command with product_name: Chicken Breast.

This is not a reliable product-selection workflow. The resolved product exists only as an LLM inference from unstructured assistant text; it is not represented as typed commerce state. The command also does not express a deliberate selection or a subsequent business operation.

Why This Matters

Customers will naturally use references such as:

the first one

second option

that chicken

add it to my cart

The system must resolve these references deterministically against the most recent relevant product results. It must not depend on an LLM rereading formatted product text and guessing the intended product.

Desired Outcome

After a product search, the system should retain enough typed commerce context to support later product references in the same conversation.

When the customer refers to one of the returned products, the system should resolve that reference against the retained context and make the selected product available to the next appropriate workflow. The result must survive restoration of the existing thread-based LangGraph conversation.

Constraints

Preserve the frozen FastAPI + LangGraph architecture.

Preserve the planner → command → handler → capability flow.

LangGraph remains responsible for orchestration, messages, and checkpointing.

ConversationState remains framework independent.

Business/commerce context must be explicit and typed; do not use a generic dict[str, Any] as a business-state container.

Capabilities remain outside the graph; do not turn each capability into a LangGraph node.

Prompt builders remain independent from LangGraph.

LangChain remains isolated behind adapters.

Do not redesign existing runtime foundations or make unrelated refactors.

Scope

Define the behaviour and state required for retaining recent product-search results across turns.

Define the behaviour for resolving an ordinal product reference, such as first one, against those results.

Make the resolved selection available as structured commerce context for future workflows.

Ensure the necessary context participates correctly in existing conversation restoration.

Add focused automated tests for the behaviour.

Non-Goals

Adding an item to a cart.

Creating or updating cart domain models.

Checkout, payment, inventory reservation, or order creation.

Changing the catalog-search business rules unless necessary to expose the structured search result.

Broad runtime redesign.

Acceptance Criteria

Given a successful product search with multiple products, a later first one reference resolves to the first product from that result set.

The resolution uses structured retained context, not parsing the prior assistant response text.

The selected product is represented in typed commerce state and is available after the next graph invocation using the same thread_id.

An ordinal that has no corresponding product result does not silently select a product; the system follows the existing clarification/response behaviour.

Existing greeting and direct product-search flows continue to work.

The implementation includes focused tests for same-turn and restored-conversation behaviour.

Evidence

Observed planner behaviour:

USER: I want chicken
ASSISTANT: Available products:
Chicken Breast - ₹320.00/kg
Chicken Wings - ₹220.00/kg
USER: I want first one

Planner decision:
EXECUTE_CAPABILITY search_product
arguments={"product_name": "Chicken Breast"}

The warning below is a separate compatibility concern that must be assessed during planning, but it is not the core functional problem:

Deserializing unregistered type runtime.planner.response.PlannerResponse
from checkpoint. This will be blocked in a future version.

Questions for the Planning Phase

What is the smallest typed commerce-session model that satisfies this issue and supports the next cart workflow?

Which layer should resolve ordinal references so the LLM does not act as the source of truth for product identity?

How should the current checkpoint serialization warning be addressed without coupling domain models to LangGraph?

Which planner commands or capabilities are needed now, and which should be deferred until the cart specification?
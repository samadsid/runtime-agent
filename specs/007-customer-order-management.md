Customer Order Management Specification

Status: Approved for implementation after fulfilment and inventoryPrerequisites: 005-checkout-order-lifecycle.md, 006-order-fulfilment-inventory.mdScope: Customer order history, order details, and safely confirmed order cancellation.

1. Goal

Complete the first post-purchase customer-management slice:

List my orders
→ View one order
→ Request cancellation
→ Explicitly confirm cancellation
→ Release reserved inventory
→ Return the persisted result

The customer graph remains unchanged:

Planner → Execute → Response → END

This milestone extends commerce capabilities and domain services. It does notintroduce new graph nodes or expose staff fulfilment operations to customers.

2. Scope

Included

Listing the current conversation's recent orders.

Viewing complete customer-safe details for one order.

Resolving an order by displayed ordinal, explicit order reference, or “latest”.

Two-step customer cancellation with explicit confirmation.

Customer cancellation only while the order is CONFIRMED.

Transactional release of active inventory reservations on cancellation.

Idempotent repeated cancellation.

Status-history audit entry for customer cancellation.

Localized success, missing-input, invalid-reference, not-found, andcancellation-denied responses.

Excluded

Staff authentication, authorization, dashboard, and status-update API.

Customer cancellation after PREPARING begins.

Order editing, partial cancellation, returns, refunds, and substitutions.

Cart quantity editing, checkout correction, reorder, and online payment.

Cross-conversation customer accounts and consolidated account-level history.

New LangGraph nodes or custom memory tables.

3. Identity and Access Boundary

Customer identity is still conversation-scoped for this milestone.

Rules:

Every order query must include conversation_id at repository/service level.

An order reference alone is never sufficient to authorize access.

A customer cannot read or cancel an order belonging to another conversation.

Return the same customer-safe not-found outcome for an unknown order and anorder outside the current conversation.

Account-wide history is deferred until customer authentication exists.

4. Session State

Extend checkpointed CommerceSession with:

recent_order_results: tuple[OrderSummary, ...] = ()
pending_order_cancellation: PendingOrderCancellation | None = None

4.1 OrderSummary

Field

Type

Purpose

order_id

UUID

Durable order identity.

status

OrderStatus

Current persisted status snapshot.

created_at

datetime

Display and ordering.

item_count

integer

Customer-safe summary.

total_amount

Decimal

Calculated from immutable order-item snapshots.

4.2 PendingOrderCancellation

Field

Type

Purpose

order_id

UUID

Exact order awaiting confirmation.

requested_at

datetime

Traceability and optional expiry policy.

This state is short-term interaction state and belongs in the LangGraphcheckpoint. Orders, reservations, and cancellation results remain authoritativein PostgreSQL.

Never infer the cancellation target from assistant text. Resolve it fromstructured recent-order results or pending_order_cancellation.

5. Repository Extensions

Extend the commerce-domain OrderRepository contract:

async def list_for_conversation(
    self,
    conversation_id: UUID,
    limit: int,
) -> tuple[OrderSummary, ...]: ...

async def get_for_conversation(
    self,
    conversation_id: UUID,
    order_id: UUID,
) -> Order | None: ...

async def get_latest_for_conversation(
    self,
    conversation_id: UUID,
) -> Order | None: ...

Query rules:

Order lists are sorted by created_at DESC, with id DESC as a stable tie-breaker.

List queries are bounded; the initial default is 5 and maximum is 10.

Order details include immutable item snapshots, delivery details, paymentmethod, status, timestamps, and customer-safe status history where applicable.

Infrastructure converts asyncpg.Record values into dictionaries/domainmodels before returning them.

No new database table is required for listing or reading orders. Add indexesthrough Alembic only if the existing (conversation_id, created_at) access pathis not already indexed.

6. Domain Services

6.1 CustomerOrderService

Create or extend a framework-independent service with:

async def list_orders(
    self,
    conversation_id: UUID,
    limit: int = 5,
) -> tuple[OrderSummary, ...]: ...

async def get_order_details(
    self,
    conversation_id: UUID,
    order_id: UUID,
) -> Order: ...

async def cancel_confirmed_order(
    self,
    conversation_id: UUID,
    order_id: UUID,
) -> Order: ...

cancel_confirmed_order must:

load and lock the order scoped by conversation_id;

return the order unchanged if it is already CANCELLED;

allow customer cancellation only from CONFIRMED;

reject PREPARING, OUT_FOR_DELIVERY, DELIVERED, and other terminal states;

release every active reservation exactly once;

update the order to CANCELLED;

append a status-history record with actor_type = CUSTOMER;

commit the order, reservation, inventory, and history changes atomically.

The service may reuse the existing fulfilment transition infrastructure, but itmust enforce the stricter customer policy before invoking the shared transition.

7. Capabilities

7.1 list_orders

Purpose: Show recent orders belonging to the current conversation.

Arguments:

Argument

Required

Rule

limit

no

Integer from 1 to 10; default 5.

Behaviour:

Load recent orders through CustomerOrderService.

Store their summaries in CommerceSession.recent_order_results in display order.

If none exist, return a generated not-found outcome.

Otherwise return one approved item fragment per order with a 1-based ordinal.

Each item includes order reference, created date, current status, item count, andtotal amount. Protected business values must remain exact in the Response Node.

7.2 get_order_details

Purpose: Show one customer-owned order.

Arguments:

order_reference: str | None = None
ordinal: int | None = None
latest: bool = False

Exactly one target mode must be used:

order_reference resolves an explicit durable order reference;

ordinal resolves only against recent_order_results;

latest=true loads the current conversation's latest order.

If no target can be resolved, return one focused generated follow-up. If anordinal is invalid, show only the available recent-order options. Never interpretan order ordinal as a product-result or cart ordinal.

The outcome returns approved fragments for:

order reference and status;

item name, quantity, unit price, and item amount;

total amount;

payment method;

delivery name, phone number, and address;

relevant timestamps.

7.3 cancel_order

Purpose: Request and confirm cancellation of one customer-owned order.

Arguments:

order_reference: str | None = None
ordinal: int | None = None
latest: bool = False
confirmed: bool = False

First invocation: cancellation request

When confirmed is false:

resolve the exact order using reference, recent-order ordinal, or latest;

load the current persisted order;

reject cancellation if the status is not CONFIRMED;

store PendingOrderCancellation(order_id=...) in checkpointed session state;

return an approved order summary and exactly one explicit cancellation question;

do not mutate the order or inventory.

Second invocation: explicit confirmation

When confirmed=true:

require pending_order_cancellation;

use its structured order_id; never infer the target from assistant text;

call CustomerOrderService.cancel_confirmed_order;

clear pending cancellation after a successful or already-cancelled outcome;

return a generated localized result.

An ambiguous response such as “okay” does not authorize cancellation. The plannermust route only explicit cancellation confirmation to confirmed=true.

7.4 Cancellation rejection

If the order is PREPARING or later, return a grounded outcome explaining thatself-service cancellation is no longer available and direct the customer to theconfigured support path. Do not promise that staff will cancel it.

8. Planner Routing Rules

Add semantic routing rules that apply across every language, script, spelling,and mixed-language chat style:

- When the customer asks to see their orders or order history, execute
  `list_orders`.
- When the customer asks for details of an order by reference, recent displayed
  ordinal, or “latest”, execute `get_order_details` with the matching target.
- When the customer asks to cancel an order, execute `cancel_order` with the
  resolved target and confirmed=false.
- When a pending order cancellation exists and the customer explicitly confirms
  cancellation, execute `cancel_order` with confirmed=true and no inferred target.
- Never treat an order ordinal as a product-result or cart ordinal.
- Never cancel an order directly from the first cancellation request.
- A customer status inquiry remains `get_order_status`; it must not be routed to
  cancellation or a staff transition.

9. Response Localization

Every capability outcome is a GeneratedExecutionOutcome and passes through theexisting Response Node.

The Response Node must:

match the customer's language, script, tone, and chat style;

preserve order references, product names, statuses, prices, quantities, units,dates, phone numbers, and addresses exactly as approved;

translate only surrounding explanatory text and follow-up questions;

localize not-found, invalid-target, cancellation-review, cancellation-success,already-cancelled, and cancellation-denied responses;

ask exactly one explicit question when cancellation confirmation is pending.

10. Idempotency and Concurrency

Repeated confirmed cancellation of an already-cancelled order returns the samecancelled order without releasing inventory twice.

Cancellation locks the order and active reservations before mutation.

Concurrent staff/customer transitions cannot both commit incompatible states.

A failed cancellation transaction changes neither order status, inventorybalance, reservation status, nor status history.

Listing and details are read-only and never change order or session business data,except for updating recent_order_results in checkpointed short-term state.

11. Acceptance Criteria

A customer can list their five most recent orders in stable newest-first order.

A customer can view details using an explicit reference, displayed ordinal, or latest.

Order lookup never returns an order from another conversation.

The first cancellation request never mutates the order.

Only explicit confirmation of the structured pending order can cancel it.

Customer cancellation succeeds only from CONFIRMED.

Successful cancellation releases reservations and restores sellable inventory once.

Repeated cancellation is idempotent.

Cancellation failure rolls back all related writes.

All customer-facing outcomes are localized through the Response Node.

The graph remains Planner → Execute → Response → END.

No customer capability can move an order to PREPARING, OUT_FOR_DELIVERY,or DELIVERED.

12. Required Tests

List orders returns only the current conversation's orders, newest first.

List orders enforces default and maximum limits.

Get details resolves reference, ordinal, and latest targets.

Invalid and cross-conversation references return customer-safe not-found outcomes.

Cancellation request stores pending state without database mutation.

Ambiguous acknowledgement does not confirm cancellation.

Explicit confirmation cancels a CONFIRMED order transactionally.

Cancellation rejects PREPARING, OUT_FOR_DELIVERY, and DELIVERED orders.

Repeated cancellation does not release inventory twice.

Concurrent cancellation and fulfilment transition preserve one valid final state.

Order history/details/cancellation messages localize English, Roman-scriptHinglish, and Devanagari Hindi while preserving protected values.

13. Deferred Customer Milestones

After this specification is verified, continue customer-flow completion in this order:

cart quantity update and clear-cart capabilities;

checkout delivery-detail correction and checkout abandonment;

stock-aware search and confirmation recovery UX;

reorder using current catalog data and prices;

online payment lifecycle;

staff authentication and fulfilment APIs.
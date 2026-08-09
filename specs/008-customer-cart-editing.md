Customer Cart Editing Specification

Status: Approved for implementation after customer order managementPrerequisites: 004-cart-persistence-memory-localization.md, 007-customer-order-management.mdScope: Persisted cart quantity updates and explicitly confirmed cart clearing.

1. Goal

Allow customers to safely edit the active persisted cart before checkout:

View cart
→ Change an item's quantity
→ Request clear cart
→ Review exact cart
→ Explicitly confirm
→ Clear persisted items

The customer graph remains unchanged:

Planner → Execute → Response → END

No new graph nodes, staff APIs, order mutations, or inventory reservations areintroduced.

2. Scope

Included

Updating one active-cart item's quantity using its displayed 1-based ordinal.

Resolving an exact product-name reference against structured current cart items.

Persisting quantity changes transactionally.

Requesting and explicitly confirming clearing of the complete active cart.

Binding clear confirmation to the exact cart and cart version reviewed.

Invalidating checkout state whenever the cart changes.

Refreshing the checkpointed CommerceSession.cart_items snapshot after persistence.

Localized outcomes for success, empty cart, invalid ordinal, invalid quantity,stale cart, missing confirmation, and persistence failures.

Excluded

Removing an individual item; the existing remove_from_cart capability remains authoritative.

Using quantity zero as an alias for removal.

Closing or deleting the active cart record when clearing its items.

Inventory reservation during cart editing.

Checkout detail correction, reorder, online payment, and staff-side work.

New LangGraph nodes or custom memory tables.

3. Core Rules

PostgreSQL is authoritative for carts and cart items.

CommerceSession.cart_items is only a checkpointed planning/response snapshot.

Cart item ordinals are 1-based and belong only to the current displayed cart.

Product-result ordinals and order ordinals are separate namespaces.

Never resolve an item from prior assistant prose.

Persist the mutation before returning a success outcome.

Cart editing does not reserve, release, or consume inventory.

A cart change invalidates any in-progress checkout review and collected delivery details.

4. Cart Versioning

Clear-cart confirmation must not clear a cart that changed after the customerreviewed it.

Add or use a monotonic version on the active cart:

carts.version BIGINT NOT NULL DEFAULT 0

Increment version for every persisted cart mutation:

add or replace item;

update quantity;

remove item;

clear items.

If the column does not exist, add it through Alembic. Existing carts begin atversion 0.

The domain Cart model exposes version: int.

5. Session State

Extend checkpointed CommerceSession with:

pending_cart_clear: PendingCartClear | None = None

PendingCartClear

Field

Type

Purpose

cart_id

UUID

Exact active cart reviewed by the customer.

cart_version

integer

Version reviewed before confirmation.

requested_at

datetime

Traceability and optional expiry.

Pending state is short-term interaction state and belongs in the LangGraphcheckpoint. It is not a business record and requires no custom table.

Clear pending state when:

the clear succeeds;

the customer explicitly declines;

the referenced cart no longer exists;

the cart version changed and a fresh review is required.

Do not clear a newly created or modified cart using an old pending confirmation.

6. Repository Contract Extensions

Extend the commerce-domain CartRepository with business-level operations:

async def update_item_quantity_by_ordinal(
    self,
    conversation_id: UUID,
    ordinal: int,
    quantity: Decimal,
) -> Cart: ...

async def clear_active_cart(
    self,
    conversation_id: UUID,
    cart_id: UUID,
    expected_version: int,
) -> Cart: ...

Quantity update transaction

Lock the active cart.

Load cart items in their canonical display order.

Resolve the 1-based ordinal against the locked rows.

Reject an invalid ordinal without mutation.

Validate quantity is greater than zero before repository execution.

If the quantity is unchanged, return the existing cart as an idempotent no-op.

Otherwise update the item, increment cart version, and return the refreshed cart.

Clear transaction

Lock the active cart scoped by conversation_id and cart_id.

Compare its current version with expected_version.

On mismatch, raise StaleCartError without deleting anything.

Delete every cart item in the active cart.

Increment cart version once.

Keep the active cart record available for future additions.

Return the now-empty cart.

Repository implementations return domain models, not asyncpg.Record values.

7. Cart Service

Extend CartService:

async def update_item_quantity(
    self,
    conversation_id: UUID,
    ordinal: int,
    quantity: Decimal,
) -> Cart: ...

async def clear_cart(
    self,
    conversation_id: UUID,
    cart_id: UUID,
    expected_version: int,
) -> Cart: ...

The service maps persistence failures to stable domain exceptions:

CartNotFoundError;

CartItemOrdinalError;

InvalidCartQuantityError;

StaleCartError.

Capabilities map these exceptions to approved generated outcomes. SQL and rowlocking remain inside infrastructure repositories.

8. update_cart_item_quantity Capability

Purpose: Replace the quantity of one existing active-cart item.

Arguments:

ordinal: int
quantity: Decimal

Validation:

ordinal is a strict integer greater than or equal to 1;

quantity is finite and greater than zero;

product name and unit are not accepted as persistence arguments;

the unit comes from the persisted product/cart item.

Planner resolution may map a product-name reference to an ordinal only when itmatches exactly one structured current cart item. The capability still receivesthe resolved ordinal.

Examples:

Customer message

Structured cart

Command

First item ko 3 kg kar do

displayed cart exists

ordinal=1, quantity=3

Chicken Breast 5 kg kar do

one exact Chicken Breast item

resolved ordinal, quantity=5

Isko 2 kg kar do

multiple items and no unique reference

clarification; do not guess

Behaviour:

validate arguments;

call CartService.update_item_quantity;

reset checkout state to NONE after a successful mutation;

clear any pending_cart_clear because the reviewed cart changed;

replace CommerceSession.cart_items with the persisted returned cart items;

return a generated success outcome with exact product, quantity, and unit.

An unchanged quantity is a successful idempotent outcome and does not incrementthe cart version.

9. clear_cart Capability

Purpose: Review and explicitly confirm removal of every item from the active cart.

Arguments:

confirmed: bool = False

First invocation: request

When confirmed is false:

load the authoritative active cart;

if empty or missing, return a generated empty-cart outcome;

store PendingCartClear(cart_id, cart_version, requested_at) in session state;

return one approved fragment per current cart item;

ask exactly one explicit clear-cart confirmation question;

do not mutate PostgreSQL cart data.

Second invocation: confirmation

When confirmed=true:

require pending_cart_clear;

use only its structured cart ID and version;

call CartService.clear_cart;

on success, clear pending state and reset checkout state to NONE;

replace CommerceSession.cart_items with the empty persisted result;

return a generated localized confirmation.

If no pending state exists, do not infer a cart from conversation text. Return agrounded missing-confirmation outcome.

Stale cart handling

If the cart version changed after review:

do not clear any item;

clear the stale pending state;

load and return the current cart summary;

ask whether the customer wants to clear this updated cart;

store a fresh pending state only as part of that new review.

10. Checkout Interaction

Any successful cart mutation invalidates the current checkout snapshot.

After update, remove, add, or clear:

checkout = CheckoutState(stage=CheckoutStage.NONE)

This clears source cart review state and collected delivery details so the nextcheckout uses the latest persisted cart.

Do not allow READY_TO_CONFIRM checkout state to survive a cart mutation.

11. Planner Routing Rules

Add language-independent semantic rules:

- When the customer asks to change the quantity of a displayed cart item,
  execute `update_cart_item_quantity` with its cart ordinal and new quantity.
- Resolve an exact product name only against structured current cart items.
- Never use a product-result ordinal or order ordinal for cart editing.
- Quantity zero means invalid quantity; do not silently convert it to removal.
- When the customer asks to empty or clear the complete cart, execute
  `clear_cart` with confirmed=false.
- When pending_cart_clear exists and the customer explicitly confirms clearing,
  execute `clear_cart` with confirmed=true.
- Never clear the cart on the first request or an ambiguous acknowledgement.
- Individual item deletion remains `remove_from_cart`.

These rules apply to every supported language, script, spelling, and mixed-language style.

12. Response Localization

All outcomes are GeneratedExecutionOutcome values and pass through the existingResponse Node.

The Response Node must:

match customer language, script, tone, and chat style;

preserve product names, quantities, units, prices, cart ordinals, and fragment IDs;

localize update success, invalid quantity, invalid ordinal, empty cart, clearreview, stale cart, and clear success messages;

ask exactly one question when explicit clear confirmation is required.

13. Idempotency and Concurrency

Updating an item to its existing quantity is an idempotent no-op.

Repeating clear confirmation after pending state is cleared does not clear a future cart.

Clear confirmation is valid only for the reviewed cart ID and version.

Concurrent cart mutation and clear confirmation result in a stale-cart outcome,not unintended deletion.

A failed transaction changes neither cart items nor cart version.

Success is returned only after PostgreSQL commits.

14. Acceptance Criteria

A customer can update a persisted cart item by valid displayed ordinal.

An exact unique cart product-name reference resolves to the correct ordinal.

Invalid, missing, zero, negative, infinite, or ambiguous quantities do not mutate the cart.

Updating quantity refreshes session cart state and invalidates checkout state.

The first clear request returns a review and does not mutate the cart.

Explicit confirmation clears only the exact reviewed cart version.

A changed cart cannot be cleared using stale pending confirmation.

Clearing keeps the active cart record and removes all its items transactionally.

Repeated confirmation cannot clear newly added items.

All outcomes are localized through the Response Node.

Cart, product-result, and order ordinal namespaces remain separate.

The graph remains Planner → Execute → Response → END.

15. Required Tests

Quantity update resolves and persists a valid ordinal.

Exact unique product-name reference maps to the correct cart ordinal.

Invalid and ambiguous targets return approved options without mutation.

Zero, negative, infinite, missing, and malformed quantities fail validation.

Same-quantity update is idempotent and does not increment version.

Successful update increments version and resets checkout state.

Clear request stores pending state without database mutation.

Ambiguous acknowledgement does not clear the cart.

Explicit confirmation clears the reviewed version and increments version once.

Concurrent mutation produces StaleCartError and preserves current items.

Repeated old confirmation cannot clear a later cart state.

Persistence failure rolls back item and version changes.

English, Roman-script Hinglish, and Devanagari Hindi responses preserve protected values.

16. Deferred Customer Milestones

After this specification is verified:

checkout delivery-detail correction and checkout abandonment;

stock-aware confirmation recovery UX;

reorder using current catalog data and current prices;

online payment lifecycle;

staff authentication and fulfilment APIs.
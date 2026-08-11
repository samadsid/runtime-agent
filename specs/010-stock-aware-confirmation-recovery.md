Stock-Aware Order Confirmation Recovery Specification

1. Purpose

Make final cash-on-delivery confirmation safe and recoverable when inventory haschanged since the customer added products to the cart.

The system must revalidate every cart item against authoritative PostgreSQL inventoryinside the confirmation transaction. When any requested quantity is unavailable, itmust create no order, reserve no stock, close no cart, and return customer-safe recoverychoices grounded in the current inventory state.

2. Frozen Architecture and Invariants

The graph remains:

Planner -> Execute -> Response -> END

Do not add a LangGraph node.

The planner selects one action; it never changes carts, orders, or inventory.

Capabilities validate typed arguments and delegate business operations.

Commerce services own business decisions and transactions.

Repositories and PostgreSQL own persistence and locking.

PostgreSQL is authoritative for carts, orders, and inventory.

LangGraph checkpointing stores messages and short-term CommerceSession only.

Trusted tenant_id and conversation_id come from runtime context, never fromLLM-generated capability arguments.

The Response Node localizes approved meaning into the latest customer's language,script, tone, and chat style.

Product-result, cart-item, and order ordinals remain separate namespaces.

3. Existing Domain Rules

This milestone extends the existing behavior rather than replacing it:

Cart operations do not reserve stock.

Authoritative availability is checked at final order confirmation.

sellable_quantity = on_hand_quantity - reserved_quantity.

Confirmation is explicit, transactional, and idempotent by source cart.

Successful confirmation creates one order from immutable cart-item snapshots,creates idempotent inventory reservations, and closes the source cart.

Reservation identity is unique by (order_id, product_id).

Inventory reservations use the existing ACTIVE, RELEASED, and CONSUMEDlifecycle.

Cart mutations are versioned and invalidate an existing checkout review.

Stale reviewed-cart confirmation must not mutate durable state.

4. Scope

4.1 Included

Revalidate every cart item during final confirmation.

Return structured shortages for unavailable and partially available products.

Keep confirmation all-or-nothing.

Let the customer reduce a cart item to the currently sellable quantity.

Let the customer remove an unavailable cart item through existing cart operations.

Let the customer review the cart again or abandon checkout.

Handle one or multiple shortages without guessing a customer choice.

Protect against concurrent confirmations and stock changes.

Preserve confirmation idempotency and tenant isolation.

Localize every shortage and recovery response.

Add unit, repository, concurrency, planner, and integration tests.

4.2 Excluded

Automatic partial fulfilment.

Automatically substituting another product.

Automatically reducing or removing an item.

Backorders, waitlists, or replenishment notifications.

Stock reservation when an item is added to the cart.

Editing confirmed orders.

Reordering from previous orders.

Online payments.

Staff authentication and staff fulfilment endpoints.

5. Domain Model

5.1 Stock shortage

Add a customer-safe domain value object:

class StockShortage(BaseModel):
    product_id: UUID
    product_name: str
    unit: str
    requested_quantity: Decimal
    available_quantity: Decimal

Rules:

requested_quantity > 0.

available_quantity >= 0.

available_quantity < requested_quantity.

Name and unit are approved product/cart snapshot values, not LLM-generated values.

Decimal quantities must never be converted through binary floating point.

5.2 Confirmation result

Use a typed service result instead of exceptions for expected availability conflicts:

ConfirmedOrderResult = OrderConfirmed | StockUnavailable | StaleCheckout

Recommended shapes:

class OrderConfirmed(BaseModel):
    order: Order


class StockUnavailable(BaseModel):
    cart_id: UUID
    cart_version: int
    shortages: tuple[StockShortage, ...]


class StaleCheckout(BaseModel):
    cart_id: UUID | None
    reason: StaleCheckoutReason

Expected stock shortages are normal business outcomes and must not be logged asapplication exceptions.

5.3 Recovery state

Extend checkpointed checkout state only if the planner needs ordinal recovery choices:

class StockRecoveryState(BaseModel):
    cart_id: UUID
    cart_version: int
    shortages: tuple[StockShortage, ...]


class CheckoutState(BaseModel):
    # existing fields remain unchanged
    stock_recovery: StockRecoveryState | None = None

This is a short-lived display snapshot. It is never authoritative inventory data.Every recovery mutation and later confirmation must reload the cart and inventory fromPostgreSQL.

6. Confirmation Transaction

Extend the existing confirmed-order repository/service transaction. The operation mustreceive trusted identity and exact checkout source identity:

async def create_confirmed_order_from_cart(
    tenant_id: UUID,
    conversation_id: UUID,
    cart_id: UUID,
    expected_cart_version: int,
    customer_name: str,
    phone_number: str,
    delivery_address: str,
) -> ConfirmedOrderResult: ...

Adapt naming to the existing interface, but do not weaken the identity or versionrequirements.

6.1 Required transactional sequence

In one PostgreSQL transaction:

Check whether an order already exists for source_cart_id = cart_id.

If it exists, return that order as the idempotent success result.

Lock the tenant-scoped source cart row.

Verify the cart belongs to tenant_id and conversation_id.

Verify it is ACTIVE, non-empty, and has version = expected_cart_version.

Lock all required inventory rows in one deterministic order, sorted by product ID.

Compute current sellable quantity for every cart item.

Collect every shortage; do not stop after the first one.

If any shortage exists, return StockUnavailable and commit no mutation.

Otherwise create the order and immutable order-item snapshots.

Create or verify the existing idempotent ACTIVE reservation for every item.

Close the cart as CHECKED_OUT.

Commit and return the confirmed order.

The shortage path performs reads and locks only. It must not create placeholder orders,create reservations, change inventory totals, increment the cart version, or close thecart.

6.2 Concurrency requirements

Lock inventory rows in deterministic product-ID order to reduce deadlocks.

Concurrent confirmation attempts must not oversell inventory.

Concurrent retries for the same source cart must return the same order.

A concurrent cart mutation that changes the reviewed version must returnStaleCheckout, not confirm unseen contents.

A concurrent order for another cart may win the available stock. The losingtransaction returns fresh shortages after acquiring its locks.

Database uniqueness constraints remain the final idempotency guard.

7. Customer Recovery Operations

The system must never choose a recovery operation on the customer's behalf.

7.1 Reduce to available quantity

Reuse or extend the tenant-scoped cart quantity update operation. Do not introduce aspecial inventory-writing capability.

The customer can select a shortage and explicitly accept its current availablequantity. Required input:

class AcceptAvailableQuantityArguments(BaseModel):
    shortage_ordinal: int = Field(strict=True, ge=1)

Add accept_available_quantity only if the existing cart quantity capability cannotsafely express this intent. It must:

resolve the ordinal only against checkout.stock_recovery.shortages;

reload and lock the tenant-scoped active cart;

require the cart version stored in recovery state;

re-read current sellable inventory;

reject the operation if available quantity is now zero;

set the cart quantity to min(previously_offered, currently_sellable) only afterexplicit customer acceptance;

increment the cart version through the existing cart mutation path; and

reset checkout/recovery state so the customer must review checkout again.

Do not silently increase a quantity if availability has risen. The accepted quantitycannot exceed the quantity shown in the approved recovery option.

7.2 Remove an unavailable item

Use the existing remove_from_cart capability and current cart-item ordinal. Never passa shortage ordinal as a cart ordinal. After removal, reset checkout state and require anew cart review.

7.3 Review or abandon

view_cart reloads and displays the current persisted cart.

Existing checkout starts a fresh review using the current cart version.

Existing abandon_checkout clears short-term checkout state and preserves the cart.

8. Capability Outcomes

8.1 confirm_order

Map service results to generated outcomes:

Service result

Status

Required meaning

OrderConfirmed

SUCCESS

Existing confirmed-order response

StockUnavailable

CONFLICT or existing equivalent

All shortages and recovery choices

StaleCheckout

CONFLICT or existing equivalent

Cart changed; review it again

If ExecutionStatus.CONFLICT does not exist, add it or use the repository's establishedbusiness-conflict status consistently. Do not represent expected shortages as internalfailure.

Recommended approved IDs:

Meaning

ID

Shortage summary

order-stock-unavailable

Each shortage item

stock-shortage-{ordinal}

Recovery question

choose-stock-recovery

Stale checkout

checkout-cart-changed

Accepted available quantity

cart-quantity-reduced-to-available

Availability changed during recovery

stock-availability-changed

Each shortage fragment must include exact approved product name, requested quantity,available quantity, and unit. Zero availability must be explicit.

8.2 Recovery options

Options may include:

reduce a partially available item to the displayed available quantity;

remove an unavailable or short item;

review the cart; or

abandon checkout.

Options are invitations, not executable side effects. The planner executes onecapability only after the customer chooses.

9. Planner Routing

Add mandatory rules:

Explicit final confirmation executes confirm_order once.

A stock-conflict response must not be treated as a confirmed order.

When the customer chooses a numbered shortage option, resolve it only against themost recent stock-recovery options.

Never turn a shortage ordinal into a product-search, product-result, cart-item, ororder ordinal.

An explicit request to accept the shown available amount executesaccept_available_quantity or the equivalent safe cart update.

An explicit request to remove an item executes existing remove_from_cart using thecurrent cart ordinal, not the shortage ordinal.

A request to see the cart executes view_cart.

A request to stop checkout executes abandon_checkout.

If the customer refers ambiguously to one of several shortages, ask exactly oneclarification question.

Never automatically substitute products, split orders, reduce quantities, or removeitems.

After any cart mutation, require checkout review and explicit confirmation again.

These rules apply to all languages, scripts, informal spelling, transliteration, andmixed-language chat styles.

10. Response Composition and Localization

Compose the final response only from approved fragments, follow-up, and options.

Match the latest customer's language, script, tone, and chat style.

Preserve product names, prices, quantities, units, option numbers, and availabilityexactly as approved.

Translate only surrounding explanatory text.

Prefer list layout when several shortages or choices are present.

Ask exactly one clear question when a follow-up exists.

Never say an order is confirmed on a shortage or stale-checkout result.

Never promise future availability or infer a substitute.

Deterministic fallback must contain all approved shortage fragments and the approvedfollow-up in order.

Example approved meaning:

Chicken Breast: requested 5 kg; currently available 3 kg.
Would you like to reduce it to 3 kg, remove it, review your cart, or stop checkout?

The actual customer-facing wording is localized by the Response Node.

11. Persistence and Migration

Prefer no schema change if the completed inventory milestone already contains:

tenant-scoped inventory rows;

on-hand and reserved quantities;

inventory reservation rows and lifecycle status;

unique (order_id, product_id) reservation identity;

unique orders.source_cart_id; and

versioned active carts.

If any required database constraint is missing, add it through Alembic before enablingthis flow. Do not create application-owned tables through startup DDL. LangGraphcheckpointer tables remain outside application Alembic migrations.

StockRecoveryState is checkpointed short-term state and requires no application table.

12. Security, Privacy, and Observability

Scope every cart, inventory, order, and reservation query by trusted tenant_id wherethe table supports tenancy.

Never accept tenant, conversation, cart, product, order, or inventory identity fromunconstrained LLM text when runtime/session state already owns it.

Do not expose internal stock-row IDs, reservation IDs, lock details, or databaseerrors to customers.

Do not log delivery phone numbers or addresses.

Emit structured metrics/events for confirmation success, stock conflict, shortageitem count, stale checkout, idempotent retry, and concurrency retry.

Product IDs may be used in internal logs; customer-visible responses use approvedproduct names.

13. Error Handling

Missing inventory row: treat as zero sellable quantity and report a shortage; do notinvent availability.

Negative/corrupt inventory invariant: roll back, alert internally, and return a safetemporary failure rather than confirming.

Empty active cart: return existing empty-cart outcome.

Cart missing, checked out, or owned by another conversation: return a safe stale ornot-found outcome without leaking existence.

Cart version mismatch: return stale checkout and require review.

Deadlock or serialization failure: retry the complete transaction only under theexisting bounded repository retry policy.

Retry exhaustion: return a safe temporary failure; never report confirmation unlessthe durable order is loaded successfully.

Response-model failure: use deterministic approved fallback.

14. Test Requirements

14.1 Domain and service tests

Full availability returns confirmation success.

Partial availability returns an exact shortage.

Zero availability returns an exact shortage.

Multiple short items return every shortage in deterministic cart order.

One shortage prevents all order, reservation, inventory, and cart mutations.

Existing order for the source cart returns idempotent success before stock failure.

Stale cart version returns stale checkout.

14.2 Repository and concurrency tests

Confirmation locks all inventory rows in deterministic order.

Two carts competing for limited stock cannot oversell.

Two confirmations for the same cart create one order only.

A concurrent cart edit prevents confirmation of the stale review.

Shortage rollback leaves no order or reservation rows and keeps the cart ACTIVE.

Queries cannot cross tenant or conversation boundaries.

14.3 Recovery tests

Accepting an offered partial quantity updates the cart transactionally.

Recovery rechecks inventory before changing quantity.

Available quantity falling to zero prevents the reduction and returns fresh meaning.

Available quantity increasing does not silently increase the accepted amount.

Recovery with a stale cart version makes no mutation.

Removing an unavailable item uses the cart ordinal namespace.

Every successful cart mutation clears checkout and recovery state.

Abandoning checkout preserves the active cart.

14.4 Planner and response tests

English, Hindi, Romanized Hindi, and mixed-language confirmations route correctly.

Recovery choices route to exactly one appropriate capability.

Ambiguous references produce one clarification question.

The planner never selects a substitute or partial quantity automatically.

Response output preserves exact quantities and units while localizing surroundingtext.

Fallback output contains every approved shortage fragment ID in order.

15. Definition of Done

This milestone is complete when:

final confirmation revalidates all cart items under database locks;

no shortage path creates an order, reservation, inventory mutation, or cart closure;

successful confirmation remains atomic and idempotent;

concurrent transactions cannot oversell stock;

the customer receives every current shortage and explicit recovery choices;

no quantity is reduced and no item is removed without explicit customer intent;

recovery cart mutations invalidate checkout and require fresh review;

all responses and fallbacks are grounded and localized;

tenant isolation and ordinal namespaces are enforced;

all required tests pass; and

the graph remains Planner -> Execute -> Response -> END.

16. Deferred Next Milestones

Reorder from a previous order using current catalog prices and availability.

Online payment lifecycle and webhook reconciliation.

Customer authentication and saved delivery addresses.

Authenticated staff fulfilment APIs.

Customer notifications for confirmation, dispatch, delivery, and cancellation.

Production observability, security hardening, rate limiting, and deployment.
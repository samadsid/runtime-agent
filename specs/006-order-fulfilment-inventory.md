Order Fulfilment and Inventory Specification

Status: Approved for implementation after COD order completionPrerequisite: 005-checkout-order-lifecycle.mdScope: Inventory reservation, controlled staff-side fulfilment transitions,cancellation release, delivery consumption, audit history, and customer status lookup.

1. Goal

Extend confirmed cash-on-delivery orders into a deterministic fulfilment flow:

CONFIRMED → PREPARING → OUT_FOR_DELIVERY → DELIVERED
     └───────────────→ CANCELLED

Inventory is reserved when an order is confirmed, released if the order iscancelled, and consumed when the order is delivered.

The customer graph remains unchanged:

Planner → Execute → Response → END

Staff fulfilment updates use authenticated application APIs and commerce domainservices. They are not customer-chat capabilities and are not controlled by the LLM.

2. Scope

Included

Product-level inventory balances.

Atomic inventory reservation during order confirmation.

Stock-insufficient rejection before order creation succeeds.

Staff-only order transition API.

Valid transition enforcement in domain services.

Inventory release on cancellation.

Inventory consumption on delivery.

Durable order-status history and actor audit data.

Customer order-status lookup through the existing capability and Response Node.

Alembic migrations and concurrency tests.

Excluded

Online payments, refunds, and payment webhooks.

Warehouse/bin/batch/expiry-level stock.

Purchase orders, supplier receipts, stock transfers, and stock counts.

Delivery-agent assignment, route planning, and live tracking.

Returns, partial fulfilment, substitutions, and partial cancellation.

Customer-controlled fulfilment status changes.

New LangGraph nodes or inventory state in the LangGraph checkpointer.

3. Ownership Boundaries

Concern

Owner

Inventory and reservations

Commerce domain services and repositories

Order transition rules

Commerce order/fulfilment service

PostgreSQL queries and transactions

Infrastructure repositories

Staff authentication and authorization

Application/API boundary

Customer intent and status lookup

Existing planner and capability flow

Customer-facing wording

Existing Response Node

Rules:

Capabilities call domain services; capabilities do not execute SQL.

Staff APIs call the same domain services directly and do not invoke the planner.

The LLM must never authorize or perform a staff fulfilment transition.

PostgreSQL is authoritative for inventory, reservations, orders, and status history.

LangGraph checkpoint state must not duplicate inventory balances.

4. Inventory Model

4.1 InventoryBalance

Field

Type

Rule

product_id

UUID

One balance per product in this milestone.

on_hand_quantity

Decimal

Physical quantity owned by the business.

reserved_quantity

Decimal

Quantity committed to active confirmed orders.

updated_at

datetime

Updated with every stock mutation.

Derived value:

sellable_quantity = on_hand_quantity - reserved_quantity

Invariants:

on_hand_quantity >= 0
reserved_quantity >= 0
reserved_quantity <= on_hand_quantity

Cart operations do not reserve inventory. Availability is authoritative onlywhen confirmation attempts to reserve stock.

4.2 InventoryReservation

Field

Type

Rule

id

UUID

Primary identifier.

order_id

UUID

Confirmed order reference.

product_id

UUID

Reserved product.

quantity

Decimal

Greater than zero.

status

enum

ACTIVE, RELEASED, or CONSUMED.

created_at

datetime

Required.

released_at

optional datetime

Set only when released.

consumed_at

optional datetime

Set only when consumed.

One order has at most one reservation per product. Reservation mutations areidempotent:

releasing an already released reservation returns its current state;

consuming an already consumed reservation returns its current state;

a released reservation cannot be consumed;

a consumed reservation cannot be released.

5. PostgreSQL Schema

5.1 inventory_balances

product_id         UUID PRIMARY KEY REFERENCES products(id)
on_hand_quantity   NUMERIC NOT NULL CHECK (on_hand_quantity >= 0)
reserved_quantity  NUMERIC NOT NULL DEFAULT 0 CHECK (reserved_quantity >= 0)
updated_at         TIMESTAMPTZ NOT NULL

CHECK (reserved_quantity <= on_hand_quantity)

5.2 inventory_reservations

id            UUID PRIMARY KEY
order_id      UUID NOT NULL REFERENCES orders(id)
product_id    UUID NOT NULL REFERENCES products(id)
quantity      NUMERIC NOT NULL CHECK (quantity > 0)
status        TEXT NOT NULL CHECK (status IN ('ACTIVE', 'RELEASED', 'CONSUMED'))
created_at    TIMESTAMPTZ NOT NULL
released_at   TIMESTAMPTZ NULL
consumed_at   TIMESTAMPTZ NULL

UNIQUE (order_id, product_id)

Indexes:

INDEX (order_id)
INDEX (product_id, status)

5.3 order_status_history

id             UUID PRIMARY KEY
order_id       UUID NOT NULL REFERENCES orders(id)
from_status    TEXT NULL
to_status      TEXT NOT NULL
actor_id       UUID NULL
actor_type     TEXT NOT NULL
reason         TEXT NULL
created_at     TIMESTAMPTZ NOT NULL

The initial CONFIRMED history row uses from_status = NULL and an appropriatesystem/customer actor type. Every later staff transition appends one row in thesame transaction that updates the order.

Create and evolve these application-owned tables through Alembic. LangGraphcheckpointer tables remain under the supported checkpointer lifecycle.

6. Order Status Rules

Allowed transitions:

Current

Allowed next status

CONFIRMED

PREPARING, CANCELLED

PREPARING

OUT_FOR_DELIVERY, CANCELLED

OUT_FOR_DELIVERY

DELIVERED

DELIVERED

none

CANCELLED

none

Rules:

Repeating the current status is an idempotent no-op and returns the current order.

Skipping a status is rejected.

Terminal orders cannot transition.

OUT_FOR_DELIVERY → CANCELLED is excluded until a return-to-store workflow exists.

Validation belongs in the domain service, not only in the HTTP route.

7. Repository Contracts

7.1 Inventory repository

The commerce-domain interface exposes business-level transactional operations:

async def reserve_for_order(
    self,
    order_id: UUID,
    items: tuple[OrderItem, ...],
) -> tuple[InventoryReservation, ...]: ...

async def release_for_order(
    self,
    order_id: UUID,
) -> tuple[InventoryReservation, ...]: ...

async def consume_for_order(
    self,
    order_id: UUID,
) -> tuple[InventoryReservation, ...]: ...

async def get_balance(
    self,
    product_id: UUID,
) -> InventoryBalance | None: ...

7.2 Order repository extension

async def transition_status(
    self,
    order_id: UUID,
    target_status: OrderStatus,
    actor: FulfilmentActor,
    reason: str | None = None,
) -> Order: ...

async def get_status_history(
    self,
    order_id: UUID,
) -> tuple[OrderStatusHistory, ...]: ...

Repository interfaces must return domain models, not asyncpg.Record instances.

8. Order Confirmation with Reservation

Extend the existing idempotent create_confirmed_order_from_cart transaction.The unique orders.source_cart_id remains the durable retry key.

Transaction sequence:

Check for an existing order by source_cart_id; return it on retry.

Lock and load the source cart and cart items.

Lock all required inventory rows using SELECT ... FOR UPDATE in stableproduct_id order to reduce deadlock risk.

Calculate sellable quantity for every item.

If any item is insufficient, raise a domain InsufficientStockError androll back the entire transaction.

Create the confirmed order and immutable order-item snapshots.

Increase each inventory balance's reserved_quantity.

Insert one ACTIVE inventory reservation per order/product.

Close the cart and append the initial CONFIRMED status-history record.

Commit and return the complete order.

There must be no state where an order is confirmed without reservations, orreservations exist without their order.

Insufficient stock outcome

The confirm_order capability converts InsufficientStockError into a groundedgenerated outcome listing only affected products and current sellable quantities.The Response Node localizes the message while preserving product names,quantities, and units.

9. Fulfilment Service

Create a framework-independent FulfilmentService.

async def transition_order(
    self,
    order_id: UUID,
    target_status: OrderStatus,
    actor: FulfilmentActor,
    reason: str | None = None,
) -> Order: ...

The service must:

load and lock the order;

return the existing order for a repeated current status;

validate the transition table;

on CANCELLED, release active reservations;

on DELIVERED, consume active reservations;

update the order status;

append status history;

commit all changes atomically.

Inventory effects:

Transition

Balance change

Reservation status

Order confirmation

reserved += quantity

ACTIVE

CONFIRMED/PREPARING → CANCELLED

reserved -= quantity

RELEASED

OUT_FOR_DELIVERY → DELIVERED

on_hand -= quantity; reserved -= quantity

CONSUMED

Other valid transitions

no inventory change

remains ACTIVE

10. Staff API

Add an application-owned endpoint:

PATCH /staff/orders/{order_id}/status

Request:

{
  "status": "PREPARING",
  "reason": null
}

Requirements:

Require authenticated staff identity.

Authorize an explicit order-management permission/role.

Derive actor_id from authenticated context, never from an untrusted request field.

Validate UUID and request schema before service execution.

Return 404 for an unknown order, 409 for an invalid transition, and adomain-appropriate conflict for insufficient/inconsistent inventory state.

Never expose this operation as a customer planner capability.

Log order ID, old/new status, actor ID, and correlation/request ID withoutlogging secrets.

If staff authentication does not exist yet, implement the domain service andrepository first, then expose the endpoint only after authentication andauthorization are available. A development-only bypass must not be enabled inproduction.

11. Customer Status Lookup

Keep the existing get_order_status capability.

It reads the persisted order and returns an approved generated outcome containing:

order reference;

current status;

only customer-safe status information.

The Response Node translates surrounding wording into the customer's language,script, tone, and chat style while preserving the order reference and status.

Customers cannot use this capability to change order status.

12. Product Availability

For this milestone:

cart additions may perform a non-locking availability check for better UX;

order confirmation remains the authoritative locked stock check;

product search must not claim availability when sellable quantity is zero;

a cart does not guarantee stock until confirmation succeeds.

Do not rely only on the existing boolean Product.available when inventorybalances exist. Catalog availability must eventually derive from both productsaleability and inventory sellable quantity.

13. Failure and Concurrency Rules

Concurrent confirmations for different carts cannot reserve the same stockbeyond its sellable quantity.

A failed transaction changes neither order, cart, inventory, reservation, nor history.

Repeated confirmation for the same source cart returns the original order anddoes not reserve stock twice.

Repeated status updates to the current status do not apply inventory effects twice.

Cancellation and delivery lock the order and its active reservations.

Repository exceptions map to stable domain exceptions before reaching API or capability code.

14. Acceptance Criteria

A confirmed order has one active reservation per ordered product.

Insufficient stock prevents confirmation and rolls back every related write.

Two concurrent confirmations cannot oversell inventory.

A retry using the same source_cart_id returns the original order withoutcreating reservations again.

Only allowed fulfilment transitions succeed.

Cancellation from CONFIRMED or PREPARING releases inventory once.

Delivery consumes inventory once and makes the order terminal.

Every successful transition creates an audit/history row with its actor.

Customer status lookup returns the persisted current state and remains read-only.

Staff transitions bypass the planner and require authenticated authorization.

The customer graph remains Planner → Execute → Response → END.

No inventory balance is stored in LangGraph checkpoint state.

15. Required Tests

Reservation succeeds when every product has sufficient sellable stock.

Reservation fails atomically when any one order item lacks stock.

Concurrent reservations cannot violate inventory constraints.

Repeated source-cart confirmation is idempotent.

Valid status transitions succeed; invalid jumps and terminal transitions fail.

Repeating the current status is an idempotent no-op.

Cancellation releases active reservations exactly once.

Delivery reduces both on-hand and reserved quantities exactly once.

Released reservations cannot be consumed; consumed reservations cannot be released.

Status history records initial confirmation and every staff transition.

Staff endpoint rejects unauthenticated and unauthorized callers.

Customer planner cannot execute staff status transitions.

Customer order-status messages preserve protected values and localize surrounding wording.

16. Recommended Implementation Order

Add inventory and status-history domain models and exceptions.

Add Alembic migration for balances, reservations, and status history.

Implement PostgreSQL inventory repository with row locking.

Extend confirmed-order creation to reserve stock transactionally and idempotently.

Add fulfilment transition rules and FulfilmentService.

Implement cancellation release and delivery consumption.

Add authenticated staff status endpoint.

Update customer order-status responses.

Add concurrency, rollback, authorization, and localization tests.
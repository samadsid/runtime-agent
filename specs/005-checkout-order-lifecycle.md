Checkout and Order Lifecycle Specification

Status: Approved for implementation after persisted cartsPrerequisite: 004-cart-persistence-memory-localization.mdScope: Cash-on-delivery checkout, delivery-detail collection, durable ordercreation, confirmation, and order-status lookup.

1. Goal

Turn a persisted active cart into one confirmed, durable order without paymentintegration.

Persisted cart
→ checkout review
→ collect delivery details
→ explicit confirmation
→ create confirmed order
→ order-status lookup

The graph remains:

Planner → Execute → Response → END

Checkout state is short-term conversation state persisted by the LangGraphcheckpointer. Orders and order items are durable commerce data persisted throughPostgreSQL repositories.

2. Scope

Included

Review of a non-empty persisted cart.

Name, phone number, and delivery address collection.

Explicit final confirmation before order creation.

Cash-on-delivery orders only.

Transactional order and order-item creation.

Cart closure after a successful order.

Order status lookup.

Localized customer-facing responses through the Response Node.

Excluded

Online payment, payment links, refunds, and payment webhooks.

Inventory reservation and fulfilment assignment.

Delivery-slot selection, taxes, discounts, coupons, and shipping charges.

Order cancellation, editing, return, and refund workflows.

New LangGraph nodes or a custom memory table.

3. Domain Models

3.1 Order

Field

Type

Rule

id

UUID

Primary identifier.

conversation_id

UUID

Customer conversation boundary for this milestone.

status

OrderStatus

Initially CONFIRMED; later workflow statuses are listed below.

payment_method

text

Fixed to CASH_ON_DELIVERY.

customer_name

string

Required at confirmation.

phone_number

string

Required at confirmation.

delivery_address

string

Required at confirmation.

created_at

datetime

Required.

confirmed_at

datetime

Required for a confirmed order.

3.2 OrderItem

Field

Type

Rule

id

UUID

Primary identifier.

order_id

UUID

Parent order.

product_id

UUID

Catalog product reference.

product_name

string

Immutable product-name snapshot.

unit

string

Immutable unit snapshot.

unit_price

decimal

Immutable product-price snapshot at order creation.

quantity

decimal

Must be greater than zero.

Order items must store snapshots. A later catalog price or product-name changemust not change a historical order.

3.3 OrderStatus

Initial statuses:

CONFIRMED

Reserved future statuses:

PREPARING → OUT_FOR_DELIVERY → DELIVERED
CANCELLED

Do not implement fulfilment transitions in this milestone.

3.4 Checkout State

Add a typed CheckoutState inside CommerceSession and persist it through theLangGraph checkpointer.

Field

Type

Purpose

stage

enum

NONE, REVIEWING_CART, COLLECTING_DETAILS, READY_TO_CONFIRM

customer_name

optional string

Collected delivery detail.

phone_number

optional string

Collected delivery detail.

delivery_address

optional string

Collected delivery detail.

Checkout state is not an order and must not be persisted in orders until finalcustomer confirmation.

4. PostgreSQL Schema

4.1 orders

Column

Type

Rule

id

UUID

Primary key.

conversation_id

UUID

Required; indexed.

status

text

Required.

payment_method

text

Required; CASH_ON_DELIVERY.

customer_name

text

Required.

phone_number

text

Required.

delivery_address

text

Required.

created_at

timestamptz

Required.

confirmed_at

timestamptz

Required.

4.2 order_items

Column

Type

Rule

id

UUID

Primary key.

order_id

UUID

Foreign key to orders.id.

product_id

UUID

Product reference.

product_name

text

Required snapshot.

unit

text

Required snapshot.

unit_price

numeric

Required snapshot.

quantity

numeric

Required and greater than zero.

Constraints:

CHECK (quantity > 0)
INDEX (conversation_id, created_at DESC) ON orders
INDEX (order_id) ON order_items

Add these tables in an Alembic migration. Application-owned migrations do notmanage LangGraph checkpointer tables.

5. Repository and Service Boundaries

Create a commerce-domain OrderRepository interface and aPostgresOrderRepository infrastructure implementation.

Required operations:

async def create_confirmed_order_from_cart(
    self,
    conversation_id: UUID,
    cart_id: UUID,
    customer_name: str,
    phone_number: str,
    delivery_address: str,
) -> Order: ...

async def get_latest_order(
    self,
    conversation_id: UUID,
) -> Order | None: ...

create_confirmed_order_from_cart must run in one database transaction:

lock/load the active cart and items;

reject an empty or missing cart;

create the confirmed order;

snapshot and insert every order item;

close the active cart;

return the complete order.

The transaction must be idempotent for a repeated confirmation of the samecheckout. A retry must return the already-created order, not create another.

OrderService owns this business workflow. Capabilities call the service;they never execute SQL.

6. Capabilities

6.1 checkout

Purpose: Start checkout for the persisted active cart.

Behaviour:

Load the active cart through CartRepository.

If it is empty, return a generated empty-cart outcome.

If it contains items, update CheckoutState.stage to REVIEWING_CART.

Return approved cart-summary fragments and one follow-up asking whether thecustomer wants to proceed with checkout.

6.2 collect_delivery_details

Purpose: Save customer name, phone number, and delivery address intocheckpointed checkout state.

Arguments:

Argument

Required

Validation

customer_name

yes

Non-empty string.

phone_number

yes

Non-empty string; phone validation policy remains configurable.

delivery_address

yes

Non-empty string.

Behaviour:

Validate supplied data deterministically.

Merge valid values into immutable CheckoutState.

If any required field is absent, return one focused generated follow-up forthe next missing field.

When all fields are present, set stage to READY_TO_CONFIRM and return anapproved review with one explicit confirmation question.

6.3 confirm_order

Purpose: Create the final order only after explicit customer confirmation.

Arguments:

Argument

Required

Validation

confirmed

yes

Must be true.

Preconditions:

CheckoutState.stage is READY_TO_CONFIRM.

All delivery details are present.

An active persisted cart has at least one item.

Behaviour:

Call OrderService.create_confirmed_order_from_cart.

Return a generated success outcome with the new order reference.

Reset checkout state to NONE.

Refresh the session cart to empty/closed state.

The order database operation is named create_confirmed_order_from_cart; it isnot a separate customer-facing capability. This avoids an unnecessary extraturn between confirmation and order creation.

6.4 get_order_status

Purpose: Return the latest order status for the current conversation.

Arguments: None for the initial version.

Behaviour:

Return a generated not-found outcome when no order exists.

Otherwise return the order reference and current status.

7. Planner Routing Rules

Add capability guidance for semantic intent in every language and mixed-languagestyle:

- When the customer asks to checkout, place the order, or proceed from a cart,
  execute `checkout`.
- When checkout is collecting delivery details, execute `collect_delivery_details`
  when the customer provides required details.
- When checkout is ready to confirm and the customer explicitly agrees, execute
  `confirm_order` with confirmed=true.
- Do not create an order based on an ambiguous acknowledgement such as “okay”
  unless it is an explicit confirmation in the current confirmation context.
- When the customer asks where their order is or asks for order status, execute
  `get_order_status`.

8. Localized Responses

Every outcome from checkout and order capabilities must be aGeneratedExecutionOutcome and pass through the existing Response Node.

The Response Node must:

match the latest customer language, script, tone, and chat style;

preserve order IDs, product names, prices, quantities, units, and statuses;

translate/rephrase only surrounding explanatory wording;

localize success, empty-cart, missing-detail, invalid-detail, not-ready, andconfirmation messages.

9. Acceptance Criteria

A non-empty persisted cart can enter checkout.

An empty cart cannot enter checkout.

Delivery details are collected into checkpointed CheckoutState.

An order cannot be created without explicit confirmation and completedelivery details.

Confirming checkout creates one durable order with immutable order-itemsnapshots and closes the cart in one transaction.

Retrying the same confirmation does not create a duplicate order.

Restarting the application retains checkout state through the PostgreSQLcheckpointer and retains orders through PostgreSQL tables.

get_order_status returns the latest persisted order for the conversation.

Every customer-facing outcome is localized through the Response Node.

No payment, inventory reservation, or extra graph node is introduced.

10. Required Tests

Checkout rejects an empty cart.

Checkout returns a grounded persisted-cart summary.

Delivery-detail collection asks only for the next missing required field.

Confirmation rejects incomplete checkout state.

Confirmation creates one order and snapshots each cart item.

A duplicate confirmation is idempotent.

Cart closure and order creation roll back together on database failure.

Latest-order lookup returns the persisted status.

Any language like English, Roman-script Hinglish, and Devanagari Hindi  responses preserve ordervalues while adapting surrounding wording.
Catalog and Inventory Administration Specification

1. Purpose

Provide authenticated administrators with safe APIs and React Native screens formanaging the sellable product catalog and physical inventory without editing PostgreSQLdirectly.

This milestone extends the existing staff platform with two operational flows:

Catalog administration
    -> create or edit product
    -> activate or deactivate product
    -> publish current price and low-stock threshold

Inventory administration
    -> receive or adjust physical stock
    -> update inventory balance atomically
    -> append immutable inventory movement
    -> expose current and low-stock views

Order-driven reservation, release, and consumption remain automatic consequences ofthe existing order lifecycle. Administrators cannot manufacture those movements fromthe mobile application.

2. Prerequisites

Product and catalog browsing behavior from specification 018.

Inventory balances, reservations, and fulfilment effects from specification 006.

Authenticated staff identities, tenant memberships, roles, idempotency, and auditconventions from specification 020.

React Native staff/admin application from specification 021.

Alembic-managed PostgreSQL schema.

PostgreSQL as the authoritative catalog and inventory store.

3. Goals

Eliminate routine direct database edits for products, prices, availability, and stock.

Allow only authenticated ADMIN users to mutate catalog or physical inventory.

Keep all reads and writes tenant-scoped.

Enforce unique SKU identity within each tenant.

Preserve immutable order-item snapshots when catalog values later change.

Maintain a complete, reconcilable, append-only inventory movement ledger.

Distinguish physical stock, reserved stock, and sellable stock.

Prevent manual adjustments from making stock negative or lower than activereservations.

Make product and inventory mutations idempotent and concurrency-safe.

Record who changed catalog or stock, when, by how much, and why.

Expose low-stock information without making the mobile app download the full catalog.

Extend the existing mobile application with role-aware catalog and inventory screens.

Preserve customer Planner, Execute, and Response behavior.

4. Non-goals

Supplier accounts, purchase orders, invoices, or supplier payments.

Multi-warehouse, bin, batch, lot, serial-number, or expiry-date stock.

Product images, media upload, barcodes, label printing, or scanners.

Bulk CSV import/export in the first version.

Product variants, bundles, recipes, substitutions, or configurable modifiers.

Scheduled prices, promotions, discounts, tax calculation, or dynamic pricing.

Unit conversion, such as converting pieces to kilograms.

Stock transfers between locations.

Stock counts with approval workflows.

Editing confirmed order-item snapshots when a product changes.

Hard deletion of products, inventory balances, or movement history.

Allowing FULFILMENT_STAFF to change catalog or physical stock.

Letting an LLM interpret stock adjustments or decide inventory mutations.

5. Frozen Architecture

The customer graph remains unchanged:

Planner -> Execute -> Response -> END

Catalog and inventory administration use deterministic staff APIs:

React Native admin screen
    -> typed authenticated staff API
    -> authorize ADMIN membership
    -> validate request, version, and idempotency key
    -> catalog or inventory application service
    -> tenant-scoped PostgreSQL transaction
    -> durable response

Rules:

Do not add catalog-admin or inventory-admin nodes to LangGraph.

Admin routes never call CommerceRuntime.chat or construct planner commands.

The mobile application never connects directly to PostgreSQL.

Route handlers parse HTTP and call services; they do not implement stock arithmetic.

Services own business invariants; repositories own SQL, locking, and transactions.

The backend derives tenant_id, staff_id, and role from authenticated context.

Request bodies never supply trusted actor or tenant identity.

PostgreSQL is authoritative for products, categories, balances, movements, versions,idempotency results, and audit history.

6. Roles and Permissions

Operation

ADMIN

FULFILMENT_STAFF

List products and stock for operations

yes

optional read-only

View product and movement details

yes

optional read-only

Create product

yes

no

Edit product name, price, category, SKU, threshold

yes

no

Activate/deactivate product

yes

no

Receive stock

yes

no

Correct, damage, or waste stock

yes

no

Create reservation/release/consumption manually

no

no

Delete product or movement history

no

no

The initial mobile navigation exposes catalog and inventory only to ADMIN. The backendmust enforce every permission even if a client bypasses the UI. Read-only fulfilmentstaff access may be enabled later through an explicit permission change; it is notrequired for acceptance.

7. Catalog Domain Model

7.1 Product lifecycle

Use an explicit product status:

class ProductStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"

If the current model uses available: bool, migrate or map it consistently:

available = true  <=> status = ACTIVE
available = false <=> status = INACTIVE

Do not maintain two independently mutable fields with conflicting meaning.

Semantics:

ACTIVE: product may appear in customer catalog/search, subject to sellable stock.

INACTIVE: product is hidden from new customer discovery and cannot be newly added toa cart.

Deactivation does not delete historical order items, movements, reservations, oraudit records.

Existing active carts referencing a newly inactive product must revalidate productstatus before checkout/confirmation and return the existing safe unavailable result.

Reactivation is allowed when catalog data is valid; it does not create stock.

7.2 Product fields

class AdminProduct(BaseModel):
    id: UUID
    tenant_id: UUID
    sku: str
    name: str
    category_id: UUID | None
    price: Decimal
    currency: str
    unit: str
    status: ProductStatus
    low_stock_threshold: Decimal | None
    display_order: int
    version: int
    created_at: datetime
    updated_at: datetime

Rules:

SKU is required, trimmed, normalized for uniqueness, and unique per tenant.

Preserve a display SKU separately only if normalization changes presentation.

Name is required after trimming and bounded in length.

Price is a finite Decimal and must be greater than or equal to zero. If zero-pricedproducts are not valid for the business, configure a stricter > 0 policy.

Currency uses the application's supported uppercase currency code and cannot beinvented by the mobile client.

Unit uses a configured supported unit such as kg or piece; arbitrary new unitsrequire an explicit domain/configuration change.

Category, when present, must belong to the same tenant and be active/valid underspecification 018.

display_order is a bounded non-negative integer used by catalog browsing.

Low-stock threshold is null or a finite non-negative quantity in the product's unit.

Version starts at 1 and increments once per successful catalog mutation.

7.3 Unit immutability

Changing a unit changes the meaning of every quantity. Therefore:

Unit may be changed only before the product has any inventory movement, non-zerobalance, reservation, cart persistence, or order-item history.

Once referenced operationally, unit change returns 409 product_unit_locked.

To sell the same commercial item under a different unit, deactivate the old productand create a new SKU/product.

No automatic conversion between units is permitted.

7.4 Price updates

Price changes affect future catalog results and future cart/order validation only.

Existing confirmed order-item snapshots keep their original price, unit, currency,quantity, and product name.

Active carts must follow the existing price-revalidation policy before checkout.

Every price change records old and new values in catalog change history.

Price updates never rewrite historical order totals.

7.5 Product deletion

Products are never hard-deleted through the API. Use INACTIVE instead. This preservesforeign-key integrity, auditability, order history, and inventory ledger identity.

8. Inventory Model

The balance defined in specification 006 remains authoritative:

sellable_quantity = on_hand_quantity - reserved_quantity

Invariants:

on_hand_quantity >= 0
reserved_quantity >= 0
reserved_quantity <= on_hand_quantity
sellable_quantity >= 0

Extend the balance with:

class InventoryBalance(BaseModel):
    product_id: UUID
    tenant_id: UUID
    on_hand_quantity: Decimal
    reserved_quantity: Decimal
    sellable_quantity: Decimal
    version: int
    updated_at: datetime

sellable_quantity is derived at read time or through a database-generated/viewexpression; it is not independently mutated.

Every new product receives an inventory-balance row with:

on_hand_quantity = 0
reserved_quantity = 0
version = 1

Initial physical stock is added with a RECEIPT, ensuring the ledger explains theentire post-creation balance.

9. Inventory Movement Types

class InventoryMovementType(str, Enum):
    OPENING_BALANCE = "OPENING_BALANCE"
    RECEIPT = "RECEIPT"
    POSITIVE_CORRECTION = "POSITIVE_CORRECTION"
    NEGATIVE_CORRECTION = "NEGATIVE_CORRECTION"
    DAMAGE = "DAMAGE"
    WASTAGE = "WASTAGE"
    RESERVATION = "RESERVATION"
    RELEASE = "RELEASE"
    CONSUMPTION = "CONSUMPTION"

9.1 Movement effects

Type

On-hand delta

Reserved delta

Creator

OPENING_BALANCE

migration baseline

migration baseline

system migration only

RECEIPT

+quantity

0

admin

POSITIVE_CORRECTION

+quantity

0

admin

NEGATIVE_CORRECTION

-quantity

0

admin

DAMAGE

-quantity

0

admin

WASTAGE

-quantity

0

admin

RESERVATION

0

+quantity

order system

RELEASE

0

-quantity

order system

CONSUMPTION

-quantity

-quantity

order system

OPENING_BALANCE exists only to baseline pre-existing balances when the ledger isintroduced. It is not accepted by an API or shown as an admin action.

9.2 Staff-created movements

RECEIPT: new physical stock arrived.

POSITIVE_CORRECTION: a verified count/data error requires increasing recorded stock.

NEGATIVE_CORRECTION: a verified count/data error requires decreasing recordedstock.

DAMAGE: stock became unusable due to a specific damaging incident.

WASTAGE: stock was discarded because of spoilage, expiry, trimming, preparation, ornormal operational loss.

9.3 System-created movements

RESERVATION: confirmation commits sellable stock to an order.

RELEASE: cancellation or approved recovery makes reserved stock sellable again.

CONSUMPTION: delivery/fulfilment removes reserved physical stock.

Admin APIs must reject attempts to create OPENING_BALANCE, RESERVATION, RELEASE,or CONSUMPTION.

10. Inventory Movement Record

class InventoryMovement(BaseModel):
    id: UUID
    tenant_id: UUID
    product_id: UUID
    movement_type: InventoryMovementType
    quantity: Decimal
    on_hand_delta: Decimal
    reserved_delta: Decimal
    on_hand_before: Decimal
    on_hand_after: Decimal
    reserved_before: Decimal
    reserved_after: Decimal
    reference_type: str | None
    reference_id: UUID | None
    reason: str
    actor_type: str
    actor_id: UUID | None
    idempotency_key: str | None
    created_at: datetime

Rules:

Movement rows are append-only and immutable.

Quantity is finite and greater than zero.

Deltas are derived by the backend from movement type and quantity; clients never senddeltas or before/after values.

Manual movement reason is required, trimmed, and bounded.

System movements use a deterministic bounded reason/category, not LLM text.

reference_type/reference_id links order-system movements to a reservation, order,or migration baseline as appropriate.

System order operations use their existing durable idempotency boundary; manualmovements use the staff API idempotency key.

Before/after values must match the locked balance in the same transaction.

Movement records cannot be edited or deleted. Corrections require a new compensatingmovement with its own reason.

11. Low-stock Policy

A product is low stock when:

status = ACTIVE
and low_stock_threshold is not null
and sellable_quantity <= low_stock_threshold

Rules:

Threshold uses the product's immutable unit.

Null disables low-stock classification for that product.

Zero is valid and means the product is low only when no sellable quantity remains.

Low-stock state is derived, not stored as an independently mutable boolean.

The first version provides dashboard/list visibility only; proactive low-stocknotifications are deferred.

Catalog search availability follows existing policy and must not claim unavailablestock as sellable merely because a threshold is unset.

12. PostgreSQL Schema

Create and evolve application tables through Alembic.

12.1 Products

Extend the existing products table as needed:

status               TEXT NOT NULL DEFAULT 'ACTIVE'
low_stock_threshold  NUMERIC NULL
display_order        INTEGER NOT NULL DEFAULT 0
version              INTEGER NOT NULL DEFAULT 1
updated_at           TIMESTAMPTZ NOT NULL

Constraints/indexes:

CHECK (status IN ('ACTIVE', 'INACTIVE'))
CHECK (price >= 0)
CHECK (low_stock_threshold IS NULL OR low_stock_threshold >= 0)
CHECK (display_order >= 0)
CHECK (version >= 1)
UNIQUE (tenant_id, sku_normalized)
INDEX (tenant_id, status, category_id, display_order, name)

If the existing schema has only sku, either enforce uniqueness on an immutablenormalized representation or add sku_normalized. Do not rely on application-onlycase normalization for uniqueness.

12.2 Inventory balances

Extend the existing balance table:

tenant_id          UUID NOT NULL
version            INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1)

Required constraints:

PRIMARY KEY or UNIQUE (tenant_id, product_id)
CHECK (on_hand_quantity >= 0)
CHECK (reserved_quantity >= 0)
CHECK (reserved_quantity <= on_hand_quantity)
INDEX (tenant_id, updated_at)

The product FK and tenant relationship must prevent or transactionally reject a balancebeing associated with another tenant's product.

12.3 inventory_movements

Column

Type

Rule

id

UUID

Primary key

tenant_id

UUID

Required tenant boundary

product_id

UUID

Required product FK

movement_type

text

Supported movement enum

quantity

numeric

Finite and greater than zero

on_hand_delta

numeric

Required signed delta

reserved_delta

numeric

Required signed delta

on_hand_before

numeric

Required non-negative snapshot

on_hand_after

numeric

Required non-negative snapshot

reserved_before

numeric

Required non-negative snapshot

reserved_after

numeric

Required non-negative snapshot

reference_type

text

Nullable bounded source category

reference_id

UUID

Nullable durable source ID

reason

text

Required bounded explanation/category

actor_type

text

STAFF, SYSTEM, or existing supported actor

actor_id

UUID

Nullable; required for staff movement

idempotency_key

text

Nullable; required for staff movement

created_at

timestamptz

Required

Constraints/indexes:

CHECK (quantity > 0)
CHECK (on_hand_after >= 0)
CHECK (reserved_after >= 0)
CHECK (reserved_after <= on_hand_after)
UNIQUE (tenant_id, actor_id, idempotency_key)
UNIQUE (tenant_id, movement_type, reference_type, reference_id)
    WHERE reference_id IS NOT NULL
INDEX (tenant_id, product_id, created_at DESC, id DESC)
INDEX (tenant_id, movement_type, created_at DESC)

The source uniqueness rule may need a more precise source-operation discriminator whenone reference legitimately generates several movement types. Preserve the invariantthat one logical reservation/release/consumption effect cannot create duplicate ledgerrows.

12.4 catalog_change_history

Column

Type

Rule

id

UUID

Primary key

tenant_id

UUID

Required

product_id

UUID

Required product FK

change_type

text

CREATED, UPDATED, ACTIVATED, DEACTIVATED

from_version

integer

Nullable for creation

to_version

integer

Required

changes

jsonb

Approved changed fields with before/after values

actor_id

UUID

Authenticated admin

created_at

timestamptz

Required

Do not store arbitrary request objects. Permit only catalog fields approved for audit.History is append-only.

12.5 Staff idempotency

Reuse staff_api_idempotency from specification 020 for:

CREATE_PRODUCT
UPDATE_PRODUCT
CHANGE_PRODUCT_STATUS
ADJUST_INVENTORY

The canonical request hash must include operation, target resource when present,validated business input, and expected version. The idempotency result commits in thesame transaction as the catalog or inventory change.

13. Migration and Backfill

The migration must:

Add product status/threshold/display/version fields without breaking existingcatalog reads.

Map the existing availability field to the selected single source of truth.

Add inventory balance version and tenant constraints.

Create movement and catalog-history tables.

For each existing inventory balance, append exactly one system-generatedOPENING_BALANCE movement containing its current on-hand and reserved values.

Validate that every existing reserved quantity is non-negative and does not exceedon-hand quantity before completing.

Fail safely with diagnostics if duplicate normalized SKUs or invalid balances exist;do not silently merge products or alter stock.

Add indexes/constraints after data validation in an order appropriate to deploymentsize and locking policy.

The opening movement establishes the ledger baseline. It does not change the existingbalance. Products created after this migration start at zero and do not require anopening movement.

14. Backend API Surface

Prefix endpoints with /api/staff/v1 and apply the authentication/authorization/errorconventions from specification 020.

14.1 List products with inventory

GET /api/staff/v1/catalog/products
Authorization: Bearer <access-token>

Filters:

status;

category_id;

normalized name/SKU query;

stock_state=LOW|OUT|AVAILABLE;

bounded limit, maximum 100;

opaque cursor.

Each row may return:

product ID, SKU, name, category, price, currency, unit, status,
on-hand, reserved, sellable, threshold, product version,
inventory version, updated time

Use stable cursor pagination and database-side filters. Do not load the complete catalogto calculate stock state in application memory.

14.2 Create product

POST /api/staff/v1/catalog/products
Authorization: Bearer <access-token>
Idempotency-Key: <unique-client-key>
Content-Type: application/json

Request:

{
  "sku": "CHK-BREAST-001",
  "name": "Chicken Breast",
  "category_id": "category-uuid",
  "price": "320.00",
  "currency": "INR",
  "unit": "kg",
  "status": "INACTIVE",
  "low_stock_threshold": "10",
  "display_order": 10
}

Rules:

Admin-only.

Decimal values travel as canonical decimal strings in JSON contracts where necessaryto avoid binary floating-point loss.

Create product and zero balance atomically.

Default new products to INACTIVE unless the request explicitly activates a fullyvalid product under policy.

Initial stock is not accepted in this request; add it through RECEIPT.

SKU conflicts return a stable conflict error.

Exact replay returns the original product and balance without creating duplicates.

14.3 View product

GET /api/staff/v1/catalog/products/{product_id}
Authorization: Bearer <access-token>

Return catalog data, current balance, versions, derived stock state, and currentlypermitted admin actions. A missing or cross-tenant product returns the same 404.

14.4 Update product

PATCH /api/staff/v1/catalog/products/{product_id}
Authorization: Bearer <access-token>
Idempotency-Key: <unique-client-key>
If-Match: "<product-version>"
Content-Type: application/json

Mutable fields:

SKU, name, category, price, currency under policy, unit when unlocked,
low-stock threshold, display order

Status changes use the dedicated endpoint below. The request must include at least onefield and reject unknown fields. Successful mutation increments product version onceand appends catalog history.

14.5 Activate or deactivate product

PATCH /api/staff/v1/catalog/products/{product_id}/status
Authorization: Bearer <access-token>
Idempotency-Key: <unique-client-key>
If-Match: "<product-version>"
Content-Type: application/json

Request:

{
  "status": "INACTIVE",
  "reason": "Temporarily unavailable from supplier"
}

Reason is required and bounded. Repeating the already completed idempotent requestreturns its stored result. A new request targeting the current status is a safe no-oponly if domain policy explicitly supports it; it must not append duplicate history.

14.6 Adjust physical inventory

POST /api/staff/v1/inventory/products/{product_id}/adjustments
Authorization: Bearer <access-token>
Idempotency-Key: <unique-client-key>
If-Match: "<inventory-version>"
Content-Type: application/json

Request:

{
  "movement_type": "RECEIPT",
  "quantity": "25.5",
  "reason": "Supplier delivery reference GRN-1042"
}

Allowed request types:

RECEIPT
POSITIVE_CORRECTION
NEGATIVE_CORRECTION
DAMAGE
WASTAGE

The backend derives the delta, locks the balance, validates invariants, updates thebalance/version, appends the movement, stores idempotency result, and commits atomically.

14.7 Movement history

GET /api/staff/v1/inventory/products/{product_id}/movements
Authorization: Bearer <access-token>

Filters:

movement type;

bounded UTC date range;

opaque cursor;

bounded limit, maximum 100.

Return movement type, quantity/deltas, before/after values, reason, source referencecategory, safe actor display, and timestamp. Do not expose authentication secrets,idempotency keys, or unrestricted internal payloads.

14.8 Inventory summary

GET /api/staff/v1/inventory/summary
Authorization: Bearer <access-token>

Return tenant-scoped aggregate counts:

{
  "active_products": 20,
  "low_stock_products": 4,
  "out_of_stock_products": 2,
  "inactive_products": 3,
  "oldest_low_stock_products": []
}

The actionable list is bounded. Aggregate in PostgreSQL; do not fetch every product tothe API process or mobile client.

15. Application and Repository Contracts

15.1 Catalog service

async def create_product(
    self,
    context: StaffRequestContext,
    command: CreateProductCommand,
    idempotency: StaffIdempotencyRequest,
) -> ProductWithInventory: ...

async def update_product(
    self,
    context: StaffRequestContext,
    product_id: UUID,
    expected_version: int,
    command: UpdateProductCommand,
    idempotency: StaffIdempotencyRequest,
) -> ProductWithInventory: ...

async def change_product_status(
    self,
    context: StaffRequestContext,
    product_id: UUID,
    expected_version: int,
    status: ProductStatus,
    reason: str,
    idempotency: StaffIdempotencyRequest,
) -> ProductWithInventory: ...

15.2 Inventory administration service

async def adjust_inventory(
    self,
    context: StaffRequestContext,
    product_id: UUID,
    expected_version: int,
    movement_type: ManualInventoryMovementType,
    quantity: Decimal,
    reason: str,
    idempotency: StaffIdempotencyRequest,
) -> InventoryAdjustmentResult: ...

Use a restricted ManualInventoryMovementType at the input boundary so system-onlytypes are unrepresentable as valid admin commands.

15.3 Query repositories

Expose tenant-scoped, cursor-based product, balance, movement, and summary queries.Every method accepts trusted tenant_id. No repository API used by staff routes mayload or mutate a product using product_id alone.

15.4 Order inventory integration

Extend existing reserve/release/consume transactions to append their movement rows inthe same transaction as their current balance/reservation/order effects. Do not createa second, competing implementation of reservation arithmetic.

16. Transaction Rules

16.1 Product creation

One transaction must:

claim/validate the staff idempotency key;

validate normalized SKU uniqueness and tenant category;

insert product version 1;

insert zero inventory balance version 1;

append CREATED catalog history;

store the completed idempotent response;

commit.

16.2 Product mutation

One transaction must:

claim/validate idempotency;

lock the tenant-scoped product;

compare expected product version;

validate fields and unit lock policy;

update product and increment version;

append approved before/after catalog history;

store response;

commit.

16.3 Manual stock movement

One transaction must:

claim/validate idempotency;

load and lock tenant-scoped product and balance;

compare expected inventory version;

validate active admin membership and manual movement type;

derive signed delta;

verify resulting balance invariants, especially on_hand >= reserved;

update on-hand quantity and increment balance version;

append immutable movement with exact before/after values and actor;

store response;

commit.

No partial result may survive a failed transaction.

17. Concurrency and Idempotency

Product and inventory versions are independent.

Product metadata edit uses product If-Match; stock adjustment uses inventoryIf-Match.

A stale version returns 409 stale_product_version or409 stale_inventory_version with the current safe version and summary.

The client refreshes and asks the admin to review again; it never automaticallyresubmits changed stock against a fresh balance.

Same idempotency key plus identical canonical request returns the stored result.

Same key plus different input returns 409 idempotency_key_conflict.

Duplicate taps and ambiguous transport retries reuse one key.

Concurrent negative adjustments serialize on the balance row; at most the validmutations commit.

Database constraints remain the final protection against negative/inconsistent stock.

Existing bounded deadlock/serialization retry policy applies only where the operationis safe under the retained idempotency boundary.

18. Validation and Business Errors

Use the stable error envelope from specification 020.

HTTP

Code

Meaning

400

invalid_request

Malformed filter, cursor, or request

403

staff_access_denied

Caller is not an authorized admin

404

product_not_found

Missing or cross-tenant product

409

sku_already_exists

Normalized tenant SKU conflict

409

stale_product_version

Product metadata changed concurrently

409

stale_inventory_version

Inventory changed concurrently

409

product_unit_locked

Operational history prevents unit change

409

insufficient_unreserved_stock

Reduction would make on-hand below reserved

409

idempotency_key_conflict

Key reused with different input

422

invalid_movement_type

Admin attempted a system-only movement

422

invalid_quantity

Quantity is non-finite, zero, or negative

422

adjustment_reason_required

Manual movement has no valid reason

503

temporarily_unavailable

Safe failure after bounded retries

Do not return SQL errors, cross-tenant existence, stack traces, or internal lock data.

19. React Native Admin Experience

Extend the existing staff-mobile application.

19.1 Navigation

Admins receive additional destinations:

Dashboard
Orders
Catalog
Inventory
Account

FULFILMENT_STAFF navigation remains unchanged. Role-based hiding does not replacebackend authorization.

19.2 Catalog list

Display:

name and SKU;

active/inactive badge;

current price, currency, and unit;

sellable/on-hand/reserved quantities;

low/out-of-stock badge;

search and status/category/stock filters;

cursor pagination and pull to refresh.

19.3 Create/edit product

Use React Hook Form and runtime schemas consistent with specification 021.

Use decimal text input; never convert stock or money through binary floating-pointarithmetic.

Load valid categories and configured units from typed backend contracts.

Explain that initial stock is added separately through Receive stock.

Confirm activation/deactivation and require a reason for status changes.

Preserve form input after recoverable network errors.

On stale product version, reload current values and require the admin to review edits.

Never silently merge conflicting fields.

19.4 Product inventory detail

Display:

on hand
reserved
sellable
low-stock threshold
inventory version/update time
recent movements

Actions:

Receive stock

Positive correction

Negative correction

Record damage

Record wastage

View full movement history

Do not expose buttons for opening balance, reservation, release, or consumption.

19.5 Adjustment form

Clearly label whether the action increases or decreases on-hand stock.

Require positive quantity and non-empty reason.

Display the product unit beside quantity.

For reductions, preview the proposed on-hand value using decimal-safe display logic,while treating backend validation as authoritative.

Show current reserved quantity and warn that stock cannot be reduced below it.

Require explicit confirmation naming product, movement type, quantity, and unit.

Generate one idempotency key per logical confirmed action.

Disable duplicate submission.

Reuse the same key only for an ambiguous retry of unchanged input.

Do not optimistically mutate authoritative stock before the response.

19.6 Movement history

Show newest first:

movement type and human-readable label;

quantity and unit;

before/after on-hand and reserved values;

reason;

safe actor identity/type;

source order/reference where staff are authorized to view it;

timestamp.

Movement history is read-only. If an admin made a mistake, provide a new correctionaction rather than edit/delete.

19.7 Dashboard integration

Add low-stock and out-of-stock cards using /inventory/summary. Selecting a card opensthe filtered catalog/inventory list. Refresh affected dashboard queries after productor stock mutations.

20. Mobile State, Security, and Privacy

Reuse SecureStore authentication and session lifecycle from specification 021.

Do not persist product or movement query caches to general device storage.

Clear catalog/inventory caches on logout or session expiry.

Never log access tokens, full API payloads, adjustment reasons, idempotency keys, orcustomer/order PII.

Stock data is business-sensitive; exclude it from third-party analytics payloads.

Generate secure UUID idempotency keys using the supported native implementation.

A 401 follows the single global session-expiry flow.

A 403 refreshes identity/permissions and does not retry the mutation.

App bundle configuration contains no database credentials or signing secrets.

21. Catalog Visibility and Customer Flow

Customer catalog/search returns only active products under existing availabilitypolicy.

Newly created inactive products never appear to customers.

Activation becomes visible through normal authoritative repository reads; do not copyproduct state into prompts.

Deactivation removes a product from new discovery but preserves recent historicalassistant messages and database records.

Before selection/add/checkout, reload current product status and inventory as requiredby existing specifications.

Product name/price changes do not cause the Response Node to invent or rewritehistorical approved outcomes.

Low-stock threshold is an operational signal; it does not itself make a productunavailable unless an explicit future policy says so.

22. Audit and Reconciliation

The system must support:

opening balance
+ sum(on_hand_delta movements)
= current on_hand balance

opening reserved balance
+ sum(reserved_delta movements)
= current reserved balance

Provide an internal reconciliation query/job that detects, but does not silently repair:

balance versus movement-ledger mismatch;

reservation table versus reserved-balance mismatch;

movement before/after chain mismatch;

missing ledger event for a reservation/release/consumption;

duplicate durable source identity;

product/balance tenant mismatch.

On mismatch:

emit a safe high-severity operational event/metric;

identify tenant/product using controlled internal identifiers;

block unsafe inventory mutations when consistency cannot be established;

require explicit investigation and a documented corrective movement or migration.

Do not recalculate and overwrite production stock automatically from an ambiguoussource.

23. Observability

Low-cardinality metrics:

catalog_admin_requests_total{operation,outcome}
inventory_adjustments_total{movement_type,outcome}
inventory_adjustment_duration_seconds{movement_type}
inventory_low_stock_products{tenant_bucket_or_global}
inventory_reconciliation_failures_total{category}
catalog_concurrency_conflicts_total{resource_type}

Rules:

Do not label metrics with product ID, SKU, product name, staff ID, reason, tenant name,idempotency key, or order ID.

Structured logs may use controlled internal IDs where operationally necessary, butnever unrestricted request/response bodies.

Record safe correlation IDs and stable error categories.

Alert on repeated reconciliation failures and sustained mutation failure rates.

24. Testing Requirements

24.1 Catalog domain tests

SKU normalization and tenant-scoped uniqueness.

Same SKU is allowed in distinct tenants.

Valid create produces product, zero balance, history, and idempotency result atomically.

Product update increments version once and records only approved changed fields.

Price changes preserve historical order snapshots.

Unit change succeeds only before operational use and is locked afterward.

Activation/deactivation follows status policy and never deletes history.

Category from another tenant is rejected.

Invalid Decimal, currency, unit, threshold, status, and display order are rejected.

24.2 Inventory movement tests

Receipt increases on-hand only.

Positive correction increases on-hand only.

Negative correction, damage, and wastage decrease on-hand only.

Manual reductions cannot produce negative on-hand or on-hand below reserved.

Reservation increases reserved only.

Release decreases reserved only.

Consumption decreases both on-hand and reserved.

Admin APIs reject system-only movement types.

Every successful movement stores exact deltas and before/after values.

Movement rows cannot be updated or deleted through repositories/APIs.

Compensating corrections append new records.

24.3 Transaction and failure tests

Balance update failure creates no movement or idempotency result.

Movement insert failure rolls back balance/version.

Catalog history failure rolls back product changes.

Idempotency persistence failure rolls back business effects.

Existing order reservation/release/consumption commits its ledger row atomically.

Database constraint failures return safe errors.

24.4 Idempotency and concurrency tests

Exact same-key replay returns the original product/adjustment result.

Same key with different input is rejected.

Two admins editing one product version produce one success and one stale response.

Concurrent reductions serialize and cannot violate reserved/on-hand invariants.

Ambiguous client retry does not duplicate receipt or correction.

Deadlock/serialization retry remains bounded and effect-safe.

24.5 Authorization and tenant tests

Unauthenticated requests are rejected.

FULFILMENT_STAFF cannot use mutation endpoints.

Admin from tenant A cannot list, read, mutate, or infer tenant B products/stock.

Cross-tenant category/product references are rejected without existence leakage.

Body/query actor, role, or tenant fields cannot override trusted context.

24.6 Query and summary tests

Cursor pagination is deterministic under equal timestamps/names.

Name/SKU, status, category, and stock filters are database-scoped and bounded.

Low/out/available classifications use sellable quantity correctly.

Threshold null and zero behavior is correct.

Summary counts and bounded queues are tenant-isolated.

Query plans use intended indexes for representative catalog size.

24.7 Migration and reconciliation tests

Existing valid balances receive one opening movement without changing quantities.

Migration rejects duplicate normalized SKUs and invalid balances safely.

Upgrade and downgrade policy is documented; destructive ledger downgrade is notperformed silently.

Ledger/balance and reservation mismatch detection works.

Reconciliation observes but never silently changes stock.

24.8 React Native tests

Only admins see catalog/inventory navigation and mutation actions.

Product list filters, pagination, empty/loading/error states, and refresh work.

Create/edit/status forms validate fields and preserve recoverable input.

Adjustment form requires type, positive decimal quantity, reason, and confirmation.

System-only movement actions never render.

Mutation sends exact version and idempotency headers.

Duplicate tap sends one logical request.

Ambiguous retry reuses the same key.

Stale product/inventory conflict refreshes without automatic resubmission.

Success invalidates product, movement, summary, and relevant customer-facing caches.

Logout/session expiry clears sensitive caches and navigation.

Physical Android device verifies keyboard, decimal input, large fonts, and destructiveconfirmation UX.

25. Acceptance Criteria

This milestone is complete when:

Authorized admins can create, inspect, edit, activate, and deactivate tenant productswithout direct SQL.

Every product has exactly one tenant-valid inventory balance.

Initial/new stock is added through a receipt rather than direct balance editing.

Admins can create only approved physical-stock movements with positive quantitiesand required reasons.

Order reservation, release, and consumption automatically create correspondingimmutable ledger movements.

Current balances reconcile with opening balance plus ledger deltas.

No mutation can make on-hand/reserved/sellable quantities invalid.

SKU uniqueness, category ownership, and all queries/mutations are tenant-safe.

Product and inventory mutations are independently versioned, idempotent, and safeunder concurrency and ambiguous retry.

Product price changes never rewrite confirmed order snapshots.

Operationally used product units cannot be changed.

Products and movement records cannot be hard-deleted through the APIs.

Low-stock summary and filtered product/stock views use database aggregation.

React Native admins can complete catalog and inventory workflows on Android whilefulfilment staff remain unauthorized.

Customer Planner/Execute/Response architecture remains unchanged.

Migrations, reconciliation checks, backend tests, mobile tests, concurrency tests,and tenant-isolation tests pass.

26. Recommended Implementation Order

Audit existing product, category, inventory, reservation, and order-item schemas andidentify legacy availability/unit assumptions.

Add migrations for product status/version/threshold, balance version/tenant scope,inventory movements, catalog history, constraints, and opening-balance backfill.

Add catalog/inventory movement domain models, restricted manual movement type, andvalidation policies.

Extend order reserve/release/consume transactions to append ledger movements.

Implement reconciliation queries and tests before exposing manual mutations.

Implement tenant-scoped catalog/inventory query repositories and summary queries.

Implement admin catalog services and transaction/idempotency boundaries.

Implement manual inventory adjustment service with row locking and invariant checks.

Add authenticated admin API routes, typed schemas, stable errors, and OpenAPI tests.

Extend the React Native app with admin navigation, catalog CRUD/status screens,inventory detail, adjustments, movements, and summary cards.

Add observability, security/privacy checks, query-plan tests, and failure injection.

Run migration rehearsal, full backend/mobile test suites, and physical Androidacceptance testing.

27. Follow-up Milestones

After this specification:

Production security, deployment, secrets, CI/CD, monitoring, backups, restore drills,and disaster recovery.

A working production customer messaging channel, initially Meta WhatsApp Cloud APIwhen account setup is available.

Supplier and purchase-order workflows if real operations require them.

Multi-location inventory only after a real warehouse/location requirement exists.

Production payment provider when merchant credentials exist.

Customer OTP only when verified phone ownership becomes necessary.
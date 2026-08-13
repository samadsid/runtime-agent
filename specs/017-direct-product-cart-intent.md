Direct Product-and-Quantity Cart Intent Specification

1. Purpose

Allow a customer to add a catalog product to the active cart in one natural-languageturn when they provide a purchase intent, product description, and quantity together.

Example:

USER: I want 10 kg chicken breast
ASSISTANT: Added 10 kg Chicken Breast to your cart. Would you like to checkout or
continue shopping?

The customer must not be forced through separate search, selection, and quantity turnswhen the catalog contains one safe, unambiguous product match.

This milestone extends the existing catalog search, product selection, persisted cart,inventory-awareness, response localization, and customer-onboarding specifications. Itdoes not replace the existing add_to_cart capability.

2. Prerequisites

Product catalog persistence and tenant-scoped search.

Existing search_product, select_product, and add_to_cart capabilities.

PostgreSQL active-cart persistence from specification 004.

Stock and availability rules from specification 010.

Response composition and localization rules.

Customer onboarding and profile memory from specification 016.

Trusted runtime context containing tenant, conversation, channel, and request ID.

3. Goals

Recognize direct buy/add intent containing product and quantity.

Resolve a product only from the tenant's authoritative catalog.

Add one uniquely resolved available product in the same capability execution.

Preserve quantity and stated unit when product clarification is required.

Avoid unnecessary product search/result/selection turns.

Never guess between multiple plausible products.

Never invent a product, unit, conversion, price, availability, or stock result.

Persist cart mutation transactionally and idempotently.

Keep the frozen graph and clean architecture unchanged.

4. Non-goals

Adding several different products from one customer message.

Product bundles, modifiers, cuts, variants, substitutions, or customization unlessalready represented as independently purchasable catalog products.

Automatic unit conversion.

Quantity accumulation; existing add-or-replace cart semantics remain authoritative.

Reserving inventory at add-to-cart time unless the existing inventory specificationalready requires it.

Confirming checkout or creating an order.

Using saved customer profile details for product matching.

Calling one capability from another capability.

Adding a LangGraph node.

5. Frozen Architecture

The graph remains:

Planner -> Execute -> Response -> END

The direct intent path is:

Customer message
    -> Planner extracts product query, quantity, optional stated unit
    -> add_product_to_cart capability
    -> DirectCartService
    -> ProductRepository + CartRepository
    -> approved outcome
    -> Response Node

Rules:

The planner decides the action and extracts only explicitly supported arguments.

The capability validates typed arguments and delegates business work.

A commerce service coordinates catalog resolution and cart persistence.

Repositories own SQL, locking, and transactions.

The Response Node localizes approved meaning.

Do not implement this as search_product calling select_product callingadd_to_cart.

Reusable logic must be extracted into services used by the old and new capabilities.

6. Capability Responsibilities

Keep the distinction:

Capability

Use case

search_product

Customer asks to browse, find, check price, or check availability

select_product

Customer chooses a displayed recent product result

add_to_cart

A product is already selected and the customer supplies quantity

add_product_to_cart

Customer supplies purchase intent, product description, and quantity together

select_product_for_pending_cart_addition

Customer resolves an ambiguous direct-add result by displayed ordinal

Selection alone must not mutate the cart. Direct add mutates only after safe productresolution and validation.

7. Customer Intent Examples

7.1 Route to add_product_to_cart

Customer message

Extracted arguments

I want 10 kg chicken breast

query=chicken breast, quantity=10, unit=kg

Chicken Breast 2 kg cart mein add kar do

query=Chicken Breast, quantity=2, unit=kg

mje 5 kilo chicken breast dedo

query=chicken breast, quantity=5, unit=kilo

add 3 packs of nuggets

query=nuggets, quantity=3, unit=packs

2 chicken breast packs chahiye

query=chicken breast, quantity=2, unit=packs

The planner preserves the customer's product words. Deterministic unit normalization isperformed by policy, not invented by the LLM.

7.2 Do not route to direct add

Customer message

Correct action

Do you have chicken breast?

search_product

Chicken breast ka price kya hai?

search_product

I want chicken

Search or select flow because quantity is missing

10 kg with selected product

Existing add_to_cart

first one, 10 kg with recent results

Existing combined ordinal-selection behavior if supported; otherwise select safely

show my cart

view_cart

make Chicken Breast 10 kg when it is already displayed in cart

update_cart_item_quantity

Purchase wording alone is insufficient for direct add when product or quantity ismissing.

8. Capability Contract

8.1 add_product_to_cart

class AddProductToCartArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_query: NonEmptyText
    quantity: Decimal = Field(gt=0, allow_inf_nan=False)
    stated_unit: NonEmptyText | None = None

Argument rules:

product_query contains only the customer's catalog/product-description words.

quantity is required, finite, and greater than zero.

stated_unit is supplied only when the customer explicitly states one.

Do not accept product ID, price, currency, availability, stock, tenant ID,conversation ID, cart ID, customer profile, or request ID from the planner.

Do not accept an ordinal in this capability.

Reject unexpected fields.

Capability metadata should state that it resolves and adds only a uniquely matchingcatalog product. It must make the multiple-match clarification behavior visible to theplanner.

8.2 select_product_for_pending_cart_addition

class SelectProductForPendingCartAdditionArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ordinal: int = Field(strict=True, ge=1)

This ordinal belongs only to the current pending direct-add product options. It is not ageneral recent-search ordinal and is never a cart-item or order ordinal.

9. Unit Policy

The catalog product's canonical unit is authoritative.

Create or reuse a deterministic UnitPolicy that can normalize configured aliases:

kg, kilogram, kilograms, kilo, kilos -> kg
g, gram, grams -> g
pack, packs, packet, packets -> pack
piece, pieces, pc, pcs -> piece

The actual alias set must be configuration/domain data appropriate to the catalog; theplanner must not define conversion rules.

Rules:

Alias normalization may establish equivalence only.

Do not convert quantities between units in this milestone.

If stated_unit is equivalent to the product unit, accept it and use the canonicalcatalog unit in the cart and response.

If it conflicts with the product unit, do not mutate the cart; ask for a quantity inthe catalog unit.

If no unit is stated, use the catalog unit only when the product resolution is uniqueand the intended quantity can safely be interpreted in that sales unit.

If business policy requires explicit units for particular products, return a unitclarification instead of assuming.

Never change the product's canonical unit based on customer text.

Example mismatch:

Catalog: Chicken Nuggets — unit=pack
Customer: Add 10 kg chicken nuggets
Response meaning: Chicken Nuggets is sold by pack. How many packs would you like?

10. Product Resolution Policy

Product resolution must use the tenant-scoped authoritative catalog and deterministicbusiness thresholds. It must never use assistant prose as catalog data.

10.1 Resolution outcomes

class ProductResolutionKind(str, Enum):
    UNIQUE = "UNIQUE"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_FOUND = "NOT_FOUND"

The resolver returns catalog models or safe option projections, never invented productobjects.

10.2 Unique match

A product may be automatically resolved only when one candidate is safely dominantunder the project's catalog-search policy. Examples include:

exact normalized product-name match;

exact SKU/alias match where customer-facing SKU/aliases are supported; or

one candidate meeting an approved confidence threshold with a sufficient margin overall alternatives.

Do not ask the LLM to assign an unvalidated confidence number. Product search/resolutionpolicy owns thresholds and candidate ordering.

10.3 Ambiguous match

If multiple plausible products remain, do not add any item. Return ordered options:

Which product would you like to add?

1. Chicken Breast
2. Chicken Wings
3. Whole Chicken

The result must preserve the customer's quantity and stated unit in pending short-termstate so the customer does not repeat them.

10.4 Not found

Do not create a candidate product. Return approved not-found meaning and ask whatproduct the customer would like to search for.

10.5 Availability and stock

After unique resolution and before cart mutation:

reload the current product under the trusted tenant;

verify it is active and available;

apply the existing stock-aware cart/checkout policy;

never claim availability solely from checkpointed recent results; and

return approved unavailable/insufficient-stock behavior without mutation.

If cart-time stock checking is advisory under the existing architecture, preserve thatpolicy and perform authoritative stock reservation/deduction only at the already frozenconfirmation boundary.

11. Pending Direct-Add State

Add minimal checkpointed state:

class PendingCartProductOption(BaseModel):
    product_id: UUID
    display_name: str
    canonical_unit: str


class PendingCartAddition(BaseModel):
    options: tuple[PendingCartProductOption, ...]
    quantity: Decimal
    stated_unit: str | None
    created_at: datetime
    source_request_id: str

Add to CommerceSession:

pending_cart_addition: PendingCartAddition | None = None

Rules:

Create pending state only for an ambiguous direct-add resolution.

Store only authoritative catalog IDs and customer-safe display values needed for thenext selection.

Preserve the validated quantity and normalized/equivalent stated unit.

Do not persist pending state in cart tables.

LangGraph checkpointing owns this short-term state.

Apply a configured short expiration suitable for conversation context.

Clear it after successful selection/add, explicit cancellation, new direct-addrequest, expiration, catalog invalidation, cart checkout, or conversation reset.

A normal product search must not silently consume pending quantity.

A new direct product-and-quantity request replaces the older pending request.

12. Pending Ordinal Resolution

When pending state exists and the customer says first one, number 2, or anequivalent ordinal reference:

execute select_product_for_pending_cart_addition;

resolve only against pending_cart_addition.options;

reject out-of-range ordinals without mutation;

reload the chosen product by trusted tenant and product ID;

revalidate availability, unit, and applicable stock policy;

add/replace it using the preserved quantity;

refresh session cart state and selected product; and

clear pending state after success.

Never interpret this ordinal as:

a normal recent product-result ordinal;

a cart-item ordinal;

an order ordinal;

a saved-address ordinal; or

a status-history ordinal.

If pending state is absent or expired, ask the customer to identify the product again.Do not reconstruct the pending quantity from assistant text.

13. Commerce Service Design

Introduce a domain/application service using existing project conventions:

class DirectCartService:
    async def resolve_and_add(
        self,
        *,
        tenant_id: UUID,
        conversation_id: UUID,
        product_query: str,
        quantity: Decimal,
        stated_unit: str | None,
        request_id: str,
    ) -> DirectCartResult: ...

    async def add_pending_selection(
        self,
        *,
        tenant_id: UUID,
        conversation_id: UUID,
        product_id: UUID,
        quantity: Decimal,
        stated_unit: str | None,
        request_id: str,
    ) -> Cart: ...

The service coordinates:

ProductRepository search and reload;

deterministic ProductResolutionPolicy;

UnitPolicy;

availability/stock policy;

CartService or cart repository mutation; and

typed result mapping.

Do not duplicate cart upsert SQL or quantity rules. Extract/reuse the same cart mutationoperation used by add_to_cart.

14. Cart Persistence and Transaction Rules

For a uniquely resolved valid product, perform the existing add-or-replace semantics:

No existing cart item -> insert quantity
Existing same product -> replace with new quantity

Rules:

Scope every cart operation by trusted tenant_id and conversation_id.

Create/find the active cart and upsert the item transactionally.

Reload the authoritative product before mutation.

Preserve the catalog product ID, name, price snapshot behavior, currency, and unitaccording to the existing cart schema.

Update cart version/timestamp according to current concurrency rules.

Invalidate stale checkout review/state whenever the active cart changes.

Persist before returning success.

If persistence fails, do not return added-to-cart success.

Refresh CommerceSession.cart_items from the persisted cart.

Set selected_product to the successfully added product for natural follow-up turns.

15. Idempotency and Safe Retry

The direct add is side-effecting and must use the trusted runtime request_id at thepersistence boundary.

Requirements:

Replaying the same request returns the original successful cart result.

It must not create duplicate cart rows or apply a stale quantity twice.

Same-request replay must preserve add-or-replace semantics without incrementing cartversion unnecessarily.

Different request IDs are distinct customer actions.

Concurrent direct adds for the same cart must use existing cart locking/version rules.

A provider/network timeout with unknown result must not be made safe merely by adisabled UI button.

Idempotency belongs in atomic persistence, not planner memory.

Use the project's existing runtime idempotency table/boundary rather than creating asecond unrelated mechanism.

16. Capability Outcomes

Suggested stable IDs:

Situation

Fragment ID

Follow-up ID

Added successfully

direct-cart-item-added

checkout-or-continue

Multiple matches

direct-cart-product-ambiguous

select-product-for-cart-addition

Product not found

direct-cart-product-not-found

request-product-search

Product unavailable

direct-cart-product-unavailable

search-alternative-product

Unit mismatch

direct-cart-unit-mismatch

request-catalog-unit-quantity

Missing/invalid query

invalid-direct-cart-product

request-direct-cart-product

Invalid quantity

invalid-direct-cart-quantity

request-direct-cart-quantity

Invalid pending ordinal

invalid-pending-cart-product-ordinal

correct-pending-cart-product-ordinal

Pending selection expired

pending-cart-addition-expired

request-direct-cart-product

Temporary failure

direct-cart-temporarily-unavailable

retry-direct-cart-addition

Successful approved fragment meaning:

Added {quantity} {canonical_unit} {product_name} to your cart.

Successful follow-up meaning:

Would you like to checkout or continue shopping?

Response rules:

Preserve exact product name, validated quantity, canonical unit, price/currency whenincluded, option numbers, fragment IDs, and follow-up ID.

Localize only surrounding wording into the customer's latest language, script, tone,and chat style.

Ask exactly one follow-up question.

Do not claim the cart changed for ambiguous, invalid, unavailable, not-found, expired,or failed outcomes.

17. Planner Routing Rules

Add the following guidance to commerce routing:

Direct product-and-quantity cart rules:

- When the latest customer message clearly asks to buy or add one product and
  explicitly contains a product description and positive quantity, execute
  `add_product_to_cart`.

- Pass the customer's product-description words as `product_query`.

- Pass the explicitly supplied numeric quantity as `quantity`.

- Pass `stated_unit` only when the customer explicitly provides a unit.

- Do not execute `search_product` first merely because no product is selected.

- Do not execute `select_product` first when `add_product_to_cart` can safely
  resolve the direct request.

- When a product is already selected and the customer supplies only quantity,
  continue to execute `add_to_cart`.

- When a pending direct-cart addition exists and the customer supplies a valid
  ordinal for its displayed options, execute
  `select_product_for_pending_cart_addition`.

- Never resolve a pending direct-cart ordinal against normal search results,
  cart items, orders, addresses, or other option lists.

- Never guess between multiple product matches.

- Never invent, convert, or alter a quantity or unit.

- Do not use direct add for a price, availability, or browsing question without
  a clear cart/purchase instruction.

The planner must not decide database match confidence, availability, unit equivalence,or stock. Those are deterministic service responsibilities.

18. Interaction with Customer Onboarding

After onboarding is completed:

ASSISTANT: Your delivery details have been saved. What would you like to order?
USER: I want 10 kg chicken breast

The planner routes normally to add_product_to_cart. Saved profile fields are notpassed to the capability and are not used for product resolution.

Keep state ownership separate:

Long-term profile:
- preferred name
- unverified phone
- saved address

Active commerce state:
- selected product
- pending product clarification
- persisted active cart
- checkout state

If the first customer message contains both onboarding details and a product order,one-decision-per-execution means onboarding and cart mutation cannot both be completedby separate capabilities in the same graph pass. Supporting deferred original-intentresumption is a separate milestone unless already implemented through trusted pendingintent state. Do not silently discard or execute the order while profile review isawaiting confirmation.

19. Interaction with Existing Cart and Checkout

A successful direct add uses the same active cart as existing cart capabilities.

Existing product quantity follows current replace—not accumulate—semantics.

A successful cart change invalidates stale checkout review and confirmation state.

view_cart, removal, quantity update, clear cart, checkout, and confirmation continueunchanged.

A direct add during REVIEWING_CART, COLLECTING_DETAILS, or READY_TO_CONFIRM mustfollow the existing checkout correction/abandonment policy and must not permit staleorder confirmation.

Completed customer onboarding does not automatically start checkout.

20. Security and Privacy

Product query, quantity, and unit are commerce inputs, not identity.

Do not include saved name, phone, or address in direct-add capability arguments.

Never allow the planner to provide trusted IDs or prices.

Use parameterized PostgreSQL queries.

Apply existing input length limits to product_query and stated_unit.

Avoid logging full customer messages; structured logs may use safe outcome categories.

Do not put raw product queries or customer/channel identifiers in metric labels.

Do not expose catalog-internal scoring, stock internals, SQL errors, or stack traces tocustomers.

21. Observability

Use low-cardinality counters/events for:

direct-add requested;

unique product resolved;

ambiguous product resolution;

product not found;

unit mismatch;

product unavailable;

pending selection completed/expired;

cart mutation succeeded/failed;

idempotent result reused; and

temporary dependency failure.

Measure resolution and cart-mutation latency separately where useful. Do not use querytext, product name, phone, conversation ID, tenant ID, or request ID as metric labels.

22. Testing Strategy

22.1 Argument and unit tests

Reject missing, empty, zero, negative, infinite, NaN, and malformed quantities.

Reject empty/oversized product queries.

Accept configured unit aliases and emit canonical unit.

Reject incompatible unit without cart mutation.

Do not convert between units.

Missing stated unit follows configured product-unit policy.

22.2 Product-resolution tests

Exact chicken breast resolves one Chicken Breast product.

Case, safe whitespace, and configured alias normalization work.

Broad chicken with several products returns ordered ambiguity options.

No match returns not found without candidate creation.

Similar scores below safe dominance threshold remain ambiguous.

Tenant A cannot resolve Tenant B's product.

Archived/unavailable product cannot be added from stale search data.

22.3 Capability tests

Unique product plus valid quantity calls the service and returns success.

Ambiguous match stores pending quantity/unit and returns options.

Invalid quantity does not invoke cart persistence.

Unit mismatch returns one focused follow-up.

Not found and unavailable outcomes are grounded.

Pending valid ordinal adds the chosen product using preserved quantity.

Pending invalid ordinal preserves options and does not mutate.

Missing/expired pending state does not reconstruct data from assistant text.

Successful add refreshes cart snapshot, selected product, and clears pending state.

22.4 Repository/integration tests

Unique direct add creates one active cart and item transactionally.

Existing item quantity is replaced according to current semantics.

Persistence failure returns no success outcome.

Same request ID is idempotent.

Concurrent requests preserve database constraints and cart consistency.

Cart change invalidates stale checkout state.

Tenant and conversation isolation are enforced.

22.5 Planner tests

I want 10 kg chicken breast routes directly to add_product_to_cart.

mje 5 kilo chicken breast dedo extracts query, quantity, and stated unit.

10 kg with a selected product routes to existing add_to_cart.

Do you have chicken breast? routes to search_product, not direct add.

Chicken breast ka price? does not mutate cart.

Pending first one routes only to pending direct-add selection.

Broad/ambiguous product text is not converted into a guessed catalog product by theplanner.

Planner never supplies product ID, price, tenant, cart, request, or customer data.

22.6 Response tests

Verify success, ambiguity, not-found, unavailable, unit-mismatch, invalid-quantity,expired-pending, and temporary-failure outcomes in:

English;

Roman-script Hinglish;

Devanagari Hindi; and

at least one additional supported language.

Protected product, quantity, unit, option, price, and ID values must remain exact.

22.7 End-to-end scenarios

Unique direct add

Complete or skip onboarding according to specification 016.

Send I want 10 kg chicken breast.

Verify one add_product_to_cart decision.

Verify Chicken Breast is resolved from PostgreSQL.

Verify 10 kg is persisted before success.

Verify the localized response asks checkout or continue shopping.

Verify view cart shows the same persisted item.

Ambiguous direct add

Send I want 5 kg chicken with several chicken products.

Verify no cart mutation and options are displayed.

Send first one.

Verify only pending options are used.

Verify the chosen product is added with preserved 5 kg.

Safety scenarios

Unit mismatch.

Unavailable product.

Product removed between option display and selection.

Duplicate request delivery.

Concurrent direct additions.

Database failure.

Stale checkout invalidation.

Cross-tenant product isolation.

23. Acceptance Criteria

This milestone is complete when:

I want 10 kg chicken breast can add a uniquely matching available Chicken Breastin one capability execution without prior selection.

Product resolution uses only the authoritative tenant-scoped catalog.

Multiple plausible products cause clarification and no cart mutation.

Pending clarification preserves quantity and unit so the customer does not repeatthem.

Pending ordinals cannot cross product-result, cart, order, address, or other ordinalnamespaces.

Catalog unit equivalence is deterministic and incompatible units are never silentlyconverted.

Missing, invalid, zero, negative, infinite, or NaN quantity never changes the cart.

Successful direct add uses existing persisted add-or-replace semantics.

Cart persistence succeeds before a success response is approved.

Duplicate and concurrent execution are safe under the existing request-id and cartconcurrency boundaries.

Successful cart mutation refreshes session state and invalidates stale checkout.

Saved customer profile data is neither required nor passed into product resolution.

All outcomes are localized by the Response Node while preserving business values.

Existing search_product, select_product, add_to_cart, cart editing, checkout,order, inventory, REST, web, and WhatsApp behavior remains backward compatible.

No capability calls another capability, no SQL enters runtime/capabilities, and nonew LangGraph node is added.

Unit, planner, capability, repository, concurrency, response, and end-to-end testspass.

24. Deferred Work

Multiple distinct products in one message.

Product variants/modifiers not represented as catalog products.

Customer-approved substitutions.

Unit conversion and fractional conversion policy.

Deferred resumption of a product order supplied during onboarding.

Structured product cards or quick-reply buttons.

Recommendation ranking beyond authoritative catalog search
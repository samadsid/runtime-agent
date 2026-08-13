Catalog Browsing and Discovery Specification

1. Purpose

Allow customers to browse the authoritative product catalog when they ask generalquestions such as:

What do you have?
Aapke paas kya hai?
Menu dikhao
What chicken products are available?

General browsing must not be converted into a fabricated search query such as all,products, or *. The system must present current catalog categories or products,support pagination, preserve distinct ordinal namespaces, and let the customer safelycontinue into selection or direct cart addition.

2. Prerequisites

Tenant-scoped PostgreSQL product catalog.

Existing search_product and select_product capabilities.

Persisted cart behavior from specification 004.

Direct product-and-quantity cart intent from specification 017.

Product availability and inventory rules.

Response localization and fragment-reference validation.

LangGraph PostgreSQL checkpointing for short-term browse state.

Trusted tenant, conversation, channel, and request context.

3. Goals

Recognize general catalog, menu, assortment, and category-browsing intent.

Present a manageable set of authoritative categories or products.

Return products directly for a small catalog.

Use categories and/or pagination for a large catalog.

Support category selection and next/previous page navigation.

Keep category, browse-product, search-product, pending-add, cart, address, and orderordinals isolated.

Preserve exact names, prices, currencies, units, availability, and option numbers.

Continue naturally into product selection or specification 017's direct-add flow.

Keep all catalog retrieval deterministic and tenant isolated.

Preserve the frozen graph and architecture boundaries.

4. Non-goals

Recommendations or personalization ranking.

Semantic product substitution.

Promotions, discounts, merchandising campaigns, or sponsored ordering.

Product images, rich cards, filters, facets, or comparison UI.

Creating categories from LLM knowledge.

Adding unavailable products to a cart.

Returning the entire catalog without a configured limit.

Client-side catalog authority.

A new LangGraph node.

5. Frozen Architecture

The graph remains:

Planner -> Execute -> Response -> END

The browse path is:

Customer browse request
    -> browse_catalog capability
    -> CatalogBrowseService
    -> ProductCatalogRepository
    -> categories or paginated products
    -> checkpointed browse projection
    -> Response Node

Rules:

The planner identifies browse intent and any explicitly stated category words.

Capabilities validate typed arguments and delegate retrieval.

Services decide whether to show products or categories and own pagination policy.

Repositories provide authoritative tenant-scoped categories and products.

The Response Node localizes only approved meaning.

Do not implement browsing by calling capabilities from other capabilities.

Do not use an empty string, wildcard, or invented word with search_product.

6. Intent Routing

Customer message

Capability

What do you have?

browse_catalog

Menu dikhao

browse_catalog

What categories do you have?

browse_catalog(view="categories")

What chicken products do you have?

browse_catalog(category_query="chicken")

Do you have Chicken Breast?

search_product(query="Chicken Breast")

Chicken Breast ka price kya hai?

search_product(query="Chicken Breast")

I want 10 kg Chicken Breast

add_product_to_cart(...) from specification 017

Show my cart

view_cart

General browse intent means the customer wants to see the assortment without naming aspecific product. A named category is not automatically a named product.

7. Catalog Domain Requirements

7.1 Category model

Use an authoritative category model if the catalog already has one:

class ProductCategory(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    display_order: int
    active: bool

Products reference a category through a tenant-valid foreign key or existing equivalent.

If categories do not yet exist, add them through an Alembic migration and seed them asbusiness-owned catalog data. Do not ask the LLM to derive and persist categories fromproduct names.

7.2 Product browse projection

class CatalogProductOption(BaseModel):
    product_id: UUID
    name: str
    price: Decimal
    currency: str
    unit: str
    available: bool

Only include fields approved for customers. Do not expose cost price, supplier,inventory internals, ranking scores, or database metadata.

7.3 Availability policy

By default, browse results include only active, customer-visible, currently availableproducts. If the business chooses to display unavailable products, availability must beshown explicitly and selection/addition must still revalidate current state.

8. Small and Large Catalog Policy

Configuration owns deterministic thresholds:

CATALOG_BROWSE_PRODUCT_PAGE_SIZE=10
CATALOG_BROWSE_CATEGORY_PAGE_SIZE=10
CATALOG_BROWSE_DIRECT_PRODUCT_LIMIT=10
CATALOG_BROWSE_STATE_TTL_SECONDS=900

Rules:

When the eligible catalog has at most CATALOG_BROWSE_DIRECT_PRODUCT_LIMIT products,a general browse request returns the first product page directly.

When it exceeds that limit and active categories exist, return categories first.

When categories are unavailable by explicit business design, return a paginatedproduct list.

A category browse returns a paginated product list for that category.

Never load or render an unbounded result set.

Stable repository ordering must make repeated pages deterministic.

9. Stable Ordering

Use business-managed display order followed by stable tie-breakers:

Categories: display_order, normalized name, category ID
Products: category display_order, product display_order, normalized name, product ID

Do not let the LLM reorder products. If merchandising order is unavailable, use adocumented deterministic fallback.

10. Capability Contracts

10.1 browse_catalog

class BrowseCatalogArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_query: NonEmptyText | None = None
    view: Literal["auto", "categories", "products"] = "auto"

Rules:

category_query is supplied only from category words explicitly present in thelatest customer message.

The capability does not accept category ID, tenant ID, page number, offset, productID, availability, or display limits from the planner.

Initial page and safe page size come from deterministic service policy.

A category query must resolve against authoritative active categories.

view="categories" is used only for explicit category-list intent.

view="products" may be used for an explicit request to list all products, stillsubject to pagination.

10.2 resolve_catalog_browse

One capability owns follow-up browse actions:

class ResolveCatalogBrowseArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ordinal: int | None = Field(default=None, strict=True, ge=1)
    navigation: Literal["next", "previous"] | None = None
    cancelled: bool = False

    @model_validator(mode="after")
    def exactly_one_action(self):
        actions = (
            self.ordinal is not None,
            self.navigation is not None,
            self.cancelled,
        )
        if sum(actions) != 1:
            raise ValueError(
                "Provide exactly one of ordinal, navigation, or cancelled=true."
            )
        return self

The meaning of ordinal is determined exclusively by the currently displayed browsestate:

category page -> choose category and display its first product page;

product page -> select that product through shared selection service logic.

Navigation reloads the requested page using authoritative repository data. Cancellationclears browse state and performs no catalog or cart mutation.

11. Browse Session State

Add a single discriminated checkpoint projection:

class CatalogBrowseKind(str, Enum):
    CATEGORIES = "CATEGORIES"
    PRODUCTS = "PRODUCTS"


class CatalogCategoryOption(BaseModel):
    category_id: UUID
    name: str


class CatalogBrowseState(BaseModel):
    kind: CatalogBrowseKind
    categories: tuple[CatalogCategoryOption, ...] = ()
    products: tuple[CatalogProductOption, ...] = ()
    category_id: UUID | None = None
    page: int = Field(ge=1)
    has_previous: bool
    has_next: bool
    created_at: datetime

Add to CommerceSession:

catalog_browse: CatalogBrowseState | None = None

Invariants:

CATEGORIES contains category options and no product options.

PRODUCTS contains product options and no category options.

category_id is present only for category-filtered product browsing.

Store only the current page, not the complete catalog.

PostgreSQL remains authoritative; checkpoint options are selection context only.

Apply a configured TTL and reject expired ordinal/navigation references.

12. Ordinal Namespaces

The project now has multiple 1-based namespaces:

Namespace

Source state

Browse category

Current catalog_browse category page

Browse product

Current catalog_browse product page

Search product

recent_product_results

Pending direct add

pending_cart_addition.options

Cart item

Current displayed cart

Order

Current displayed order results

Saved address

recent_saved_addresses

Rules:

Resolve an ordinal only against the active workflow and latest displayed list.

Never copy an ordinal from one namespace into another.

When conversation state cannot identify the referenced list unambiguously, ask thecustomer to clarify.

A new displayed browse page replaces the previous browse ordinal page.

Assistant text must never be parsed to reconstruct expired options.

13. Category Resolution

An explicit category query such as chicken is resolved by a deterministictenant-scoped category resolver.

Outcomes:

exactly one safe category match -> display its first product page;

multiple category matches -> display matching category options;

no category match -> return category-not-found and current categories where useful;

inactive category -> do not browse it.

Do not silently reinterpret an unknown category as a product query. The follow-up mayask whether the customer wants to search for a product instead.

14. Pagination

Use keyset pagination where practical; offset pagination is acceptable for a smallcatalog if stable ordering and concurrency behavior are tested.

Rules:

Page size is server-configured, not planner controlled.

next is valid only when has_next is true.

previous is valid only when has_previous is true.

Invalid navigation does not change current state.

Reload each page from PostgreSQL and rebuild the page projection.

Products added or removed between pages may change the later page, but no stale optionmay be selected without an authoritative reload.

Do not expose database cursor tokens to the planner or customer.

Examples of navigation intent include next, aur dikhao, previous, and pichle.The planner maps the natural-language intent to the typed navigation literal.

15. Product Selection from Browse Results

When a customer selects a product ordinal from a browse product page:

execute resolve_catalog_browse(ordinal=N);

resolve only from the current browse product page;

reload the product under trusted tenant context;

reject deleted, inactive, or unavailable stale options;

update selected_product and recent_product_results as required by the existingselection contract;

clear or retain browse state according to one documented policy (clear is preferredafter successful selection); and

ask for quantity through the existing approved selection outcome.

Reuse product-selection service logic. Do not invoke select_product from inside thebrowse capability.

If a customer supplies ordinal and quantity together, use an existing or dedicatedtyped combined selection-and-add path. Never add to cart merely because a browse productwas displayed.

16. Direct Add and Pending-Add Interaction

A named product-and-quantity request during or after browsing routes to specification017's add_product_to_cart; it need not depend on the browse ordinal list.

Specification 017's pending-selection capability must be generalized to:

class ResolvePendingCartAdditionArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ordinal: int | None = Field(default=None, strict=True, ge=1)
    cancelled: bool = False

    @model_validator(mode="after")
    def exactly_one_action(self):
        if (self.ordinal is not None) == self.cancelled:
            raise ValueError(
                "Provide exactly one of ordinal or cancelled=true."
            )
        return self

Rename select_product_for_pending_cart_addition toresolve_pending_cart_addition so one workflow owner handles both selection andexplicit cancellation.

Cancellation behavior:

require current, unexpired pending_cart_addition;

clear only pending_cart_addition;

do not modify the persisted cart;

do not clear selected product, recent search results, or catalog browse state; and

return localized cancellation meaning with one next-action question.

Planner rules must distinguish:

cancel that add with pending direct-add state ->resolve_pending_cart_addition(cancelled=true);

stop browsing with browse state -> resolve_catalog_browse(cancelled=true);

cancel my order -> existing order-cancellation capability;

clear my cart -> existing confirmed cart-clear workflow.

17. Repository Contracts

Extend the catalog repository using project naming conventions:

async def count_browsable_products(tenant_id: UUID) -> int: ...

async def list_categories(
    tenant_id: UUID,
    *,
    page_size: int,
    cursor: CatalogCursor | None,
) -> CatalogCategoryPage: ...

async def resolve_category(
    tenant_id: UUID,
    query: str,
) -> CategoryResolution: ...

async def list_browsable_products(
    tenant_id: UUID,
    *,
    category_id: UUID | None,
    page_size: int,
    cursor: CatalogCursor | None,
) -> CatalogProductPage: ...

async def get_browsable_product(
    tenant_id: UUID,
    product_id: UUID,
) -> Product | None: ...

Every query must:

scope by trusted tenant;

enforce active/customer-visible policy;

use parameterized SQL;

use stable ordering;

return domain models, not asyncpg.Record; and

avoid unbounded reads.

18. Capability Outcomes

Suggested stable IDs:

Situation

Fragment ID

Follow-up ID

Product page

one catalog-product-{ordinal} per item

select-catalog-product

Category page

one catalog-category-{ordinal} per item

select-catalog-category

Empty catalog

catalog-empty

catalog-empty-follow-up

Empty category

catalog-category-empty

choose-another-category

Unknown category

catalog-category-not-found

choose-catalog-category

Invalid ordinal

invalid-catalog-ordinal

correct-catalog-ordinal

Next/previous unavailable

catalog-page-unavailable

continue-catalog-browse

Browse expired

catalog-browse-expired

restart-catalog-browse

Browse cancelled

catalog-browse-cancelled

catalog-next-action

Temporary failure

catalog-temporarily-unavailable

retry-catalog-browse

Pending add cancelled

pending-cart-addition-cancelled

cart-addition-next-action

Product item meaning should contain only approved fields, for example:

1. Chicken Breast - ₹320.00/kg

Category item meaning:

1. Chicken

19. Response Rules

Prefer list layout for category and product pages.

Preserve every fragment ID once and in order.

Preserve product/category names, price, currency, unit, availability, page meaning,and option numbers exactly as approved.

Localize headings, explanatory text, and exactly one follow-up question to the latestcustomer language, script, tone, and chat style.

Do not translate protected catalog names unless localized catalog fields exist asauthoritative business data.

Do not imply that a displayed item was selected or added.

Do not invent product descriptions, dietary claims, recommendations, discounts, oravailability.

Example Hinglish output:

Abhi ye products available hain:

1. Chicken Breast - ₹320.00/kg
2. Chicken Wings - ₹220.00/kg

Kaunsa chahiye?

20. Planner Routing Rules

Add:

Catalog browsing rules:

- When the customer generally asks what products, items, categories, assortment,
  or menu are available without supplying a specific product-search term,
  execute `browse_catalog`.

- Do not convert general browsing into `search_product` using an invented query
  such as `all`, `products`, `items`, `menu`, or `*`.

- When the customer asks what is available in an explicitly stated category,
  execute `browse_catalog` with those exact category words as `category_query`.

- Never invent a category. Categories and products come only from catalog
  capabilities.

- When current catalog browse state displays categories and the customer selects
  one by ordinal, execute `resolve_catalog_browse` with that ordinal.

- When current catalog browse state displays products and the customer selects
  one by ordinal, execute `resolve_catalog_browse` with that ordinal.

- When the customer requests the next or previous browse page, execute
  `resolve_catalog_browse` with the corresponding navigation action.

- When the customer explicitly stops browsing, execute
  `resolve_catalog_browse(cancelled=true)`.

- Never interpret a browse ordinal as a search result, pending cart addition,
  cart item, order, or saved address ordinal.

- When pending direct-cart state exists and the customer says `cancel that add`,
  execute `resolve_pending_cart_addition(cancelled=true)`; do not cancel catalog
  browsing, the persisted cart, or an order.

21. State Lifecycle

Create/replace browse state when:

a category page is displayed;

a product page is displayed; or

navigation successfully loads another page.

Clear browse state when:

customer explicitly cancels browsing;

product selection completes (preferred policy);

state expires;

conversation resets; or

another workflow intentionally replaces the active ordinal context under documentedsession policy.

Do not clear browse state merely because a pending direct-add is cancelled. Do not clearpending direct-add state merely because the customer browses unless the new browserequest explicitly replaces the pending workflow under planner/session policy.

22. Security, Privacy, and Tenant Isolation

Never accept tenant ID, category ID, product ID, price, page size, or cursor from LLMarguments.

Resolve stored IDs under trusted tenant context on every follow-up.

Do not expose database cursors, supplier data, stock internals, or ranking internals.

Apply configured length limits to category query.

Do not use raw queries, names, tenant IDs, conversation IDs, or customer identifiersas metric labels.

Catalog browsing uses no saved name, phone, or address.

Do not log full customer messages as routine catalog events.

23. Observability

Use low-cardinality metrics/events for:

general browse requested;

category browse requested/resolved/not found;

categories or products displayed;

next/previous page loaded/rejected;

browse selection succeeded/stale;

browse cancelled/expired;

pending direct-add cancelled;

empty catalog/category; and

repository temporary failure.

Measure repository and response latency separately where useful. Avoid product/categorynames as labels when cardinality is not strictly bounded.

24. Testing Strategy

24.1 Service and repository tests

Small catalog returns products directly.

Large catalog returns categories under auto policy.

Explicit product view remains paginated.

Category resolution is tenant scoped and deterministic.

Empty catalog/category returns typed outcomes.

Stable ordering prevents duplicates within unchanged page sequences.

Page size is server-controlled.

Inactive/hidden products and categories are excluded.

Repository returns domain models rather than database records.

24.2 Capability tests

browse_catalog stores the correct discriminated page state.

Explicit category query displays authoritative category products.

Valid category ordinal opens the first product page.

Valid product ordinal selects the reloaded product and asks quantity.

Invalid ordinal and invalid navigation do not mutate state.

Next/previous navigation updates one page only.

Expired state cannot be reconstructed from assistant text.

Browse cancellation clears only browse state.

Pending-add cancellation clears only pending direct-add state and leaves cart intact.

Mutual-exclusion validators reject multiple/no resolution actions.

24.3 Planner tests

What do you have?, Menu dikhao, and Aapke paas kya hai? route tobrowse_catalog without invented query.

What chicken products do you have? passes category words only.

Do you have Chicken Breast? routes to search_product.

I want 10 kg Chicken Breast routes to specification 017 direct add.

Browse category/product ordinals route only to current browse state.

next/aur dikhao and previous/pichle map to navigation.

cancel that add and stop browsing route to different workflow owners.

cancel my order never clears browse or pending-add state by mistake.

24.4 Response tests

Verify product pages, category pages, empty results, invalid ordinal, navigation,expiration, browse cancellation, and pending-add cancellation in:

English;

Roman-script Hinglish;

Devanagari Hindi; and

at least one additional supported language.

Exact names, values, ordinals, fragment IDs, and follow-up IDs must survive composition.

24.5 End-to-end scenarios

Small catalog

Send What do you have?.

Verify browse_catalog executes with no fabricated search query.

Verify one bounded product page is loaded from PostgreSQL.

Select first one.

Verify only the latest browse product page is used.

Supply quantity and complete existing add-to-cart flow.

Large catalog

Send Menu dikhao.

Verify a bounded category page.

Select Chicken by ordinal.

Verify a bounded Chicken product page.

Request next where available.

Select a product from the new page and verify authoritative reload.

Pending direct-add cancellation

Send I want 5 kg chicken and receive ambiguous product options.

Send cancel that add.

Verify resolve_pending_cart_addition(cancelled=true).

Verify pending state is cleared and persisted cart is unchanged.

Verify subsequent ordinal cannot reuse the cancelled pending quantity.

Repeat with stale products/categories, expiration, invalid ordinals, concurrent catalogchanges, database failure, and cross-tenant isolation.

25. Acceptance Criteria

This milestone is complete when:

General questions such as What do you have? execute browse_catalog without aninvented search query.

Small catalogs return a bounded product list directly.

Large catalogs return authoritative categories or bounded paginated products.

Explicit category requests resolve only against tenant-scoped catalog categories.

Every displayed page has deterministic ordering and isolated 1-based ordinals.

Category ordinals cannot select products, and browse-product ordinals cannot affectpending adds, carts, orders, or addresses.

Next/previous navigation is server bounded and cannot use arbitrary planner offsets.

Product selection reloads current authoritative product state before success.

Unavailable, deleted, stale, empty, and temporary-failure cases never fabricatecatalog data or mutate the cart.

cancel that add clears only pending direct-cart state throughresolve_pending_cart_addition(cancelled=true).

Browse cancellation clears only catalog browse state.

All output is localized while exact catalog values and IDs remain protected.

Catalog browsing neither reads nor exposes saved customer PII.

Existing search, selection, direct add, persisted cart, checkout, order, REST, web,and WhatsApp behavior remains backward compatible.

No capability calls another capability, no SQL enters runtime/capabilities, and noLangGraph node is added.

Unit, repository, capability, planner, response, concurrency, and end-to-end testspass.

26. Deferred Work

Product images and structured cards.

Faceted filters and sorting controls.

Product comparison.

Personalized recommendations.

Promotions and merchandising campaigns.

Customer-defined favorites or repeat-order shortcuts.

Semantic category discovery beyond authoritative aliases.

Multiple product selection in one message.
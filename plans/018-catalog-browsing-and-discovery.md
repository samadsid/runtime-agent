# Catalog Browsing and Discovery Implementation Plan

## Outcome

Implement specification 018 as two registered capabilities,
`browse_catalog` and `resolve_catalog_browse`, backed by a framework-independent
`CatalogBrowseService` and tenant-scoped product repository methods. General browse
requests will return one bounded page of authoritative products for a small catalog,
categories for a larger categorized catalog, or bounded products when categories are
not configured. Follow-up category/product ordinals and next/previous actions will
resolve only against a typed, checkpointed browse projection.

The graph remains `Planner -> Execute -> Response -> END`. No capability calls another
capability, and no LangGraph or LangChain type enters commerce models, repositories, or
services.

## Repository findings and design decisions

- Reuse and extend the existing `commerce.models.Category`; do not add a second
  category model. Add the missing `display_order` and align activation naming with
  existing project conventions while preserving a single authoritative type.
- Keep the existing lightweight `Product` model per ADR-007. Add separate browse page
  projections for customer-approved catalog fields rather than widening `Product`
  with persistence metadata such as tenant, category, or display order.
- Add catalog metadata to PostgreSQL through migration 014: active categories and
  product category membership, customer visibility, activation, and display order.
  Do not fabricate category seed data in the migration. Business-owned category data
  must be supplied separately; uncategorized catalogs use the specified paginated
  product fallback.
- Start with bounded offset pagination. It fits the specified checkpoint state, which
  stores `page` but no cursor, and permits deterministic previous-page navigation.
  Repository page requests remain server-generated and are never planner-controlled.
  Stable ordering and concurrency behavior will be documented and tested; keyset
  pagination can replace this behind the repository contract later.
- Define one explicit selection policy: after a browse product is successfully
  reloaded and selected, clear `catalog_browse`, set `selected_product`, and set
  `recent_product_results` to that one authoritative product so the existing quantity
  flow remains compatible without leaking browse ordinals into search ordinals.
- Product availability for browsing means product active, customer-visible,
  `available`, and positive sellable inventory. Every selection reload repeats those
  checks.
- Rename `select_product_for_pending_cart_addition` to
  `resolve_pending_cart_addition` in one backward-compatibility-aware change. The new
  capability contract owns ordinal selection and explicit cancellation; old planner
  naming, imports, registration, and tests are migrated together rather than keeping
  two registered workflow owners.

## Domain models and invariants

Add `commerce/models/catalog_browse.py` containing immutable, strongly typed models:

- `CatalogBrowseKind` with `CATEGORIES` and `PRODUCTS`.
- `CatalogCategoryOption(category_id, name)`.
- `CatalogProductOption(product_id, name, price, currency, unit, available)`.
- `CatalogBrowseState(kind, categories, products, category_id, page,
  has_previous, has_next, created_at)` with model validation enforcing:
  category pages contain only categories; product pages contain only products;
  `category_id` occurs only on category-filtered product pages; and page numbers start
  at one.
- Repository/service page and resolution models such as `CatalogCategoryPage`,
  `CatalogProductPage`, and a discriminated `CategoryResolution`. These carry typed
  values, never database records or generic dictionaries.

Add `catalog_browse: CatalogBrowseState | None = None` to `CommerceSession`, export the
new types from `commerce/models/__init__.py`, render only the current browse page in
`CommerceSessionRenderer`, and add every durable nested browse type to the exact
MsgPack allowlist in `runtime/graph/memory/checkpointer.py`.

The checkpoint stores only the currently displayed page. PostgreSQL remains
authoritative for identity, availability, price, category membership, and ordering.

## Database and repository work

1. Add `migrations/versions/014_catalog_browsing.py`:
   - Create tenant-scoped `product_categories` with UUID primary key, tenant ID,
     name, display order, active flag, timestamps, a tenant/name uniqueness policy,
     and indexes supporting stable active-category listing.
   - Add nullable `category_id`, `active`, `customer_visible`, and `display_order` to
     `products`; use safe defaults for existing rows and a tenant-valid composite
     foreign-key strategy so a product cannot reference another tenant's category.
   - Add indexes for tenant/category visibility filtering and deterministic order.
   - Leave existing products uncategorized unless authoritative business seed data is
     available; the runtime fallback handles that state.
2. Extend `ProductRepository` rather than introduce a competing catalog repository:
   `count_browsable_products`, `list_categories`, `resolve_category`,
   `list_browsable_products`, and `get_browsable_product`.
3. Implement the methods in `PostgresProductRepository` with parameterized SQL,
   trusted tenant scoping, inventory joins, bounded limits, and the stable order:
   categories by display order, normalized name, ID; products by category display
   order, product display order, normalized name, ID.
4. Use a small typed internal page request derived by the service from page number and
   configured size. Fetch `page_size + 1` rows to calculate `has_next`; never expose an
   offset or cursor to planner arguments or response content.
5. Update `InMemoryProductRepository` and test fakes to implement the expanded
   interface with the same filtering and stable-order semantics.

## Catalog browse service

Create `commerce/services/catalog_browse_service.py`. Inject the product repository
and an immutable policy containing product page size, category page size, and direct
product limit.

The service will own all browse decisions:

1. General `auto` browse counts eligible products. If the count is at most the direct
   limit, load product page one. If larger, load category page one and fall back to
   product page one when no active categories exist.
2. Explicit `categories` loads a bounded category page, even for a small catalog.
3. Explicit `products` loads a bounded unfiltered product page.
4. An explicit category query is length-bounded and normalized only for deterministic
   matching. One authoritative match opens product page one; multiple matches display
   the matching category options; no match returns a typed not-found result and may
   include a bounded current category page.
5. Category selection reloads the stored category under the trusted tenant and opens
   its first product page. Product selection reloads the exact stored product through
   `get_browsable_product` before returning it.
6. Navigation derives the target page from current state, rejects unavailable
   directions without mutation, reloads from PostgreSQL, and replaces the projection
   only after a successful read.
7. Translate repository failures into a typed temporary-failure result without
   changing browse or cart state.

The service returns typed result variants; capability code maps those variants to
approved response fragments and session updates.

## Capabilities and session lifecycle

### `browse_catalog`

Add `runtime/capabilities/browse_catalog/capability.py` with strict
`BrowseCatalogArguments`: optional bounded `category_query` and
`view: Literal["auto", "categories", "products"] = "auto"`, with extra fields
forbidden. Tenant, page, IDs, limits, visibility, and cursors come only from trusted
context and service policy.

Map service results to the stable fragment/follow-up IDs in the specification. Each
displayed product/category gets exactly one ordered fragment and protected exact
values. Successful pages create or replace `session.catalog_browse`; empty,
not-found, and temporary-failure outcomes never invent catalog values.

### `resolve_catalog_browse`

Add `runtime/capabilities/resolve_catalog_browse/capability.py` with strict
`ResolveCatalogBrowseArguments` and an after-validator requiring exactly one of
ordinal, navigation, or `cancelled=true`.

- Reject missing/expired state; expiration clears only `catalog_browse`.
- Resolve category ordinals only against `state.categories` and product ordinals only
  against `state.products`.
- Reject invalid ordinal/navigation with the session unchanged.
- Cancellation clears only `catalog_browse` and performs no repository/cart mutation.
- Category selection opens a fresh category product page.
- Product selection authoritatively reloads, rejects stale/unavailable products, then
  clears browse state, updates the existing selection fields, and emits the existing
  quantity question meaning.

Use an injected UTC clock and `timedelta` TTL to make expiry deterministic in tests.

### Pending direct-add rename

Move the existing implementation to
`runtime/capabilities/resolve_pending_cart_addition/`, rename its arguments and class,
set `cancelled: bool = False`, retain the exactly-one-action validator, and add the
specified cancellation follow-up `cart-addition-next-action`. Cancellation clears
only `pending_cart_addition`, preserves the persisted cart and every other ordinal
namespace, and makes no service call. Update capability names, composition-root
registration, planner rules, imports, and tests in the same commit.

## Configuration and composition

Add validated settings with the specification defaults:

- `CATALOG_BROWSE_PRODUCT_PAGE_SIZE=10`
- `CATALOG_BROWSE_CATEGORY_PAGE_SIZE=10`
- `CATALOG_BROWSE_DIRECT_PRODUCT_LIMIT=10`
- `CATALOG_BROWSE_STATE_TTL_SECONDS=900`

Validate positive bounded sizes and a positive TTL. Build `CatalogBrowsePolicy` and
`CatalogBrowseService` in `ApplicationContainer`, construct both browse capabilities,
register them in the existing capability registry, and replace the pending-add
capability registration with its renamed owner. Do not change `CommerceRuntime`,
`CommerceGraph`, graph nodes, or command handlers.

## Planner and response integration

1. Add capability names and metadata for both browse operations and the renamed
   pending-add resolver.
2. Extend `runtime/prompts/templates/commerce.md` with the exact routing boundaries
   from section 20: general browse versus named-product search versus direct add;
   explicit category words only; active browse kind controls ordinal meaning;
   next/previous navigation; and distinct browse, pending-add, order-cancel, and
   cart-clear cancellation routes.
3. Extend `CommerceSessionRenderer` with an explicit, compact active browse section
   containing kind, page availability, age/creation time, category context, and the
   exact current options. Keep browse, search, pending-add, cart, order, and address
   namespaces visibly separate.
4. Keep `ResponseNode` presentation-only. Use ordered approved fragments, options,
   protected values, and exactly one follow-up so names, prices, currencies, units,
   availability, and ordinals survive localization. Add no hardcoded language copies.

## Observability

Add a small catalog metrics/event adapter under `app/observability/` (or reuse the
project's existing metrics conventions) and instrument service/capability boundaries
for the event classes listed in section 23. Labels are limited to bounded enums such
as action, result, view, and navigation direction. Never label with tenant IDs,
conversation IDs, product/category names, queries, or full messages. Repository and
response latency remain separately measurable.

## Implementation sequence

1. Add migration 014 and evolve the existing category/catalog domain types.
2. Extend repository contracts plus in-memory and PostgreSQL implementations.
3. Implement and unit-test `CatalogBrowseService` and deterministic pagination policy.
4. Add checkpointed browse state, session rendering, and serializer allowlisting.
5. Implement `browse_catalog` and `resolve_catalog_browse` with all lifecycle paths.
6. Rename/generalize the pending direct-add resolver and preserve workflow isolation.
7. Wire settings, services, capabilities, names, registry, and application container.
8. Update planner instructions and response outcome coverage.
9. Add PostgreSQL, capability, planner, response, graph-restoration, and end-to-end
   tests, then run formatting, linting, typing, migration, and full regression checks.
10. Update `docs/architecture.md`, `docs/decisions.md`, and `docs/current-status.md`
    to record browse state authority, pagination policy, ordinal isolation, migration,
    and the completed capability surface.

## Verification matrix

### Models and validation

- Browse-state discriminator and category/product exclusivity invariants.
- Strict argument schemas reject extra fields, booleans as ordinals, zero/negative
  ordinals, and zero or multiple resolution actions.
- MsgPack and PostgreSQL checkpoint round trips preserve every browse state variant.

### Repository and service

- Small catalog returns products; large categorized catalog returns categories;
  large uncategorized catalog returns products; explicit views override auto policy.
- Empty catalog/category and exact, ambiguous, missing, inactive, and cross-tenant
  category resolution return typed results.
- Hidden, inactive, unavailable, and zero-sellable-stock products are excluded.
- Page sizes are server-controlled; unchanged page sequences have stable ordering and
  no duplicates; page boundaries behave safely under concurrent insert/removal.
- Product selection reload rejects deleted, hidden, inactive, unavailable, depleted,
  cross-tenant, or recategorized stale options.

### Capability and state isolation

- Initial browse stores only one category/product page.
- Category ordinal opens page one; product ordinal selects only from a product page.
- Next/previous replaces one page; rejected navigation and invalid ordinal preserve
  state; expiration and explicit cancellation clear only browse state.
- Successful product selection clears browse state and updates only the documented
  selection fields; it does not mutate the cart.
- Pending-add cancellation clears only pending direct-add state, makes no cart write,
  and cannot reuse its quantity later. It leaves browse, selected/search results,
  orders, addresses, and cart snapshots intact.

### Planner and response

- English, Roman Hinglish, Devanagari Hindi, and another supported language cover
  browse intent, category intent, category/product ordinals, navigation, and the
  cancellation boundaries.
- `What do you have?`, `Menu dikhao`, and `Aapke paas kya hai?` never fabricate a
  search query. Named products still search; product-plus-quantity still direct-adds.
- Product/category page, empty, unknown category, invalid ordinal, unavailable page,
  expired, cancelled, stale, and temporary-failure outcomes preserve exact fragment
  IDs, follow-up IDs, order, protected catalog values, and one localized question.

### Integration and regression

- PostgreSQL end-to-end small- and large-catalog flows, category navigation,
  authoritative selection reload, concurrent catalog changes, database failure, and
  tenant isolation.
- Existing search, select, direct-add, cart, checkout, order, REST, web chat, and
  WhatsApp suites remain green.
- Verify no new graph node, capability-to-capability call, SQL in runtime capability,
  unbounded catalog query, PII use, or cursor/ID/limit planner argument.

## Risks and explicit assumptions

- Existing installations need authoritative category assignment after migration;
  until then large catalogs intentionally use the product-page fallback.
- Offset pagination can shift under concurrent catalog edits. The contract guarantees
  bounded deterministic reads for an unchanged catalog and safe authoritative reload,
  not a frozen multi-page snapshot. This limitation is tested and documented.
- The existing `available` product field and inventory balance together define current
  sellability; the new `active` and `customer_visible` fields express catalog policy.
- Combined browse-ordinal-plus-quantity selection is deferred unless an existing typed
  path can be reused without capability chaining; plain browse selection asks for
  quantity and uses the established selected-product add flow.
- Category aliases or semantic category inference are not introduced. Resolution uses
  authoritative names and deterministic normalized matching only.


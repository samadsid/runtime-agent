Category-Led Customer Shopping Flow Specification

1. Purpose

Connect customer onboarding, durable profile memory, catalog categories, productdiscovery, cart operations, and WhatsApp identity into one coherent customer journey.

After a first-time customer saves their delivery details, the assistant must fetch anddisplay active customer-visible categories. A returning customer with a completed savedprofile must be greeted and shown the current categories immediately. Selecting acategory displays its current purchasable products and continues through the existingselection, quantity, cart, checkout, and order flows.

Category-led discovery is the default guided journey, not a mandatory detour. A customerwho states a sufficiently specific product request, direct product-and-quantity intent,cart request, order-management request, or another supported commerce intent must berouted to that intent after onboarding rather than forced to choose a category.

This milestone extends and reuses:

016-customer-onboarding-and-profile-memory.md;

017-direct-product-cart-intent.md;

018-catalog-browsing-and-discovery.md;

024-catalog-and-inventory-administration.md; and

026-meta-whatsapp-cloud-api-channel.md.

Those specifications remain authoritative for profile persistence, direct-add productresolution, category/product browsing, staff catalog administration, Meta webhooksecurity, idempotency, and provider delivery.

2. Goals

Give every stable-channel first-time customer one localized welcome and onboardingrequest before executing customer-specific commerce mutations.

Request name, phone number, and complete delivery address together as defined byspecification 016.

Store delivery details only after explicit review and confirmation.

After onboarding succeeds, fetch active categories from PostgreSQL and present themas the next guided choice.

For a returning customer, load the completed profile using trusted channel identity,greet naturally, and present current categories without recollecting details.

Show current purchasable products after category selection.

Preserve category and product ordinal namespaces and resolve them only from currentcheckpointed display state.

Support broad discovery such as What do you have? by displaying categories.

Preserve direct product search and direct product-plus-quantity cart intent withoutforcing category selection.

Preserve an actionable first-message commerce intent while onboarding is completed.

Keep all customer-facing responses in the latest customer language, script, tone, andnatural mixed-language chat style.

Keep the frozen Planner -> Execute -> Response graph.

3. Non-goals

Creating a second profile, category, product, cart, or order data model.

Guessing or generating categories from product names or LLM knowledge.

Personalized or AI-ranked categories and products.

Promotions, recommendations, sponsored ordering, bundles, modifiers, or substitutes.

Requiring category selection before every product search or repeat order.

Treating saved profile data as verified identity or verified phone ownership.

OTP authentication.

Cross-channel profile merging based only on a supplied phone number.

Persisting unconfirmed onboarding details as long-term memory.

Adding LangGraph nodes or calling one capability from another capability.

Changing checkout, payment, inventory reservation, or order fulfilment semantics.

Rich WhatsApp list messages or interactive buttons; these may be added later behindprovider-neutral approved-response contracts.

4. Frozen Architecture

The graph remains:

Planner -> Execute -> Response -> END

The application boundary hydrates trusted customer and commerce context before planning:

Channel adapter
    -> trusted CustomerChannelContext
    -> profile/session hydration
    -> Planner
    -> one capability
    -> domain service
    -> tenant-scoped repository transaction
    -> approved execution outcome
    -> Response Node

Rules:

The channel route validates and persists inbound events but does not decide onboardingor catalog behavior.

Workers pass trusted tenant, conversation, channel customer, and request identity intothe existing commerce runtime.

The planner chooses exactly one capability per graph execution.

Capabilities validate typed arguments and delegate business work to services.

Services own workflow invariants and retrieval policy.

Repositories own SQL, tenant scoping, ordering, locking, and transactions.

PostgreSQL is authoritative for completed profiles, categories, products, carts, andorders.

LangGraph checkpoint state stores only bounded pending workflow and displayed-optionprojections.

The Response Node localizes approved meaning and never chooses a category, product,price, quantity, or business operation.

5. Trusted Customer Identity

Use the existing CustomerChannelContext supplied outside LLM control:

class CustomerChannelContext(BaseModel):
    tenant_id: UUID
    conversation_id: UUID
    channel: ChannelName
    channel_customer_id: str | None
    request_id: str

For Meta WhatsApp, channel_customer_id is derived from the authenticated webhook'snormalized sender identity. Neither the planner nor customer text may override it.

Profile lookup key:

(tenant_id, channel, channel_customer_id)

Rules:

A completed saved profile means onboarding is complete for that trusted channelidentity.

A stable identity without a completed profile is a first-time/incomplete customer.

A missing stable identity remains a guest and follows specification 016's guestbehavior; do not create durable profile ownership from an arbitrary request field.

A phone number written in the message is delivery data, not channel identity.

Never expose whether another tenant or channel identity has a profile.

6. Entry Routing Policy

Before normal planner routing, the hydrated session exposes only safe workflow facts:

class CustomerJourneyProjection(BaseModel):
    has_stable_identity: bool
    onboarding_complete: bool
    has_pending_onboarding: bool
    has_pending_deferred_intent: bool

Do not expose stored phone numbers or addresses to the planner unless an existing typedprofile-confirmation workflow explicitly requires a safe projection.

Routing precedence:

Resolve an active confirmation/correction workflow that expects the latest reply.

If a stable customer is not onboarded, route to onboarding collection/review.

If onboarding has just been confirmed, route to the post-onboarding continuationpolicy in Section 9 on the following graph invocation/turn.

Resolve an existing category, product, pending direct-add, cart, checkout, or orderfollow-up using its own current state.

Route explicit supported customer intent.

For greeting, conversation start, or broad discovery with no stronger intent, showcategories.

Respond directly only when no capability can make progress.

The implementation may perform deterministic post-capability continuation within theapplication orchestration boundary only if the existing runtime already supports safemulti-step internal execution. Otherwise it asks the category question in the successfulonboarding outcome or performs browse_catalog(view="categories") on the next turn.It must not make one capability invoke another.

7. First-Time Customer Journey

7.1 First message

When a stable-channel customer has no completed profile, their first incoming text—including a greeting, broad browse request, or commerce request—must receive one welcomeand onboarding request based on specification 016.

Example:

USER: Hi
ASSISTANT: Hi! Welcome to Jhatpat AI 👋 Order aur delivery ke liye apna naam,
phone number aur complete delivery address share kar dijiye. Main in details ko future
orders ke liye save karunga.

The approved outcome must ask exactly one clear question covering all missing fields.The response must not claim verification or persistence before confirmation.

7.2 First message also contains commerce intent

Examples:

I want 10 kg chicken breast
What do you have?
Mutton ka price kya hai?
Show my last order

The onboarding requirement takes precedence for a stable identity without a completedprofile, but an actionable original intent must not be silently lost.

Store a bounded deferred intent projection in checkpoint state only when it is safe anduseful:

class DeferredCustomerIntentKind(str, Enum):
    BROWSE_CATALOG = "BROWSE_CATALOG"
    SEARCH_PRODUCT = "SEARCH_PRODUCT"
    DIRECT_CART_ADD = "DIRECT_CART_ADD"
    VIEW_CART = "VIEW_CART"
    ORDER_MANAGEMENT = "ORDER_MANAGEMENT"


class DeferredCustomerIntent(BaseModel):
    kind: DeferredCustomerIntentKind
    product_query: str | None = None
    quantity: Decimal | None = None
    stated_unit: str | None = None
    created_at: datetime

Rules:

Store only a typed, minimal projection, never the entire message or arbitrary plannerarguments.

Never store payment credentials, secrets, unrestricted personal data, prices,availability claims, database IDs supplied by the LLM, or assistant prose.

Use the same typed validation as the eventual capability.

Apply a configured TTL.

A newer explicit commerce intent may replace the older deferred intent.

A customer may explicitly cancel it.

Revalidate catalog, stock, cart, order, and tenant state when resuming it.

Do not execute a deferred side effect before onboarding confirmation.

If intent extraction is ambiguous, omit it and ask what the customer wants afteronboarding rather than guessing.

7.3 Detail collection and confirmation

All extraction, ambiguity, partial-field, review, correction, consent, and persistencerules from specification 016 remain unchanged. In particular:

accept labelled or natural unlabelled details in any order;

preserve valid pending fields;

ask for all remaining fields together;

distinguish a phone-number sequence from address text;

do not guess ambiguous name/address boundaries;

show the proposed name, phone, and address for review; and

persist only after explicit confirmation.

8. Returning Customer Journey

When a completed profile exists for the trusted channel identity:

8.1 Greeting or conversation start

Execute a customer-entry capability that returns a localized greeting and the first pageof current active categories in one approved outcome.

Example meaning:

Welcome back! What would you like to shop for?

1. Meat
2. Groceries
3. Food
4. Pharmacy

The greeting may use the saved customer name only if existing privacy and safe-profileprojection rules permit it. Never expose the saved phone number or address in a greeting.

8.2 Explicit intent on the first returning turn

A stronger supported intent takes precedence over the default category menu:

Customer message

Action

Hi

greet and show categories

What do you have?

show categories

Show categories

show categories

Show meat products

resolve category and show its products

Do you have Chicken Breast?

search_product

I want 10 kg Chicken Breast

add_product_to_cart

Show my cart

view_cart

Where is my order?

existing order-status capability

Use a different address

existing profile/checkout correction flow

Do not force an explicit product/cart/order request through the category menu.

9. Post-Onboarding Continuation

After confirm_customer_onboarding successfully saves the profile:

9.1 No deferred intent

Return approved success meaning followed by the current first page of active categories:

Your delivery details have been saved. What would you like to shop for?

1. Meat
2. Groceries
3. Food
4. Pharmacy

This must be grounded in repository results, not hardcoded prompt examples.

9.2 Deferred broad browse intent

Clear the deferred state and show current categories.

9.3 Deferred product search

Clear/claim the deferred state exactly once and perform the existing authoritative searchflow. Display the current matching products or approved not-found outcome.

9.4 Deferred direct cart-add intent

Claim the deferred request idempotently and route through specification 017'sDirectCartService. Revalidate product resolution, canonical unit, availability, stock,and active-cart state. If unique and valid, add it exactly once. If ambiguous, show thepending direct-add product choices. If invalid or unavailable, return the existing safeclarification/failure outcome.

9.5 Deferred cart or order-management intent

Execute only through the existing tenant- and customer-scoped capability and repositoryrules. A saved delivery profile does not itself prove order ownership beyond the trustedchannel/customer association already established by those specifications.

9.6 Failure safety

Persisting the profile and executing a deferred commerce mutation are separate durableoperations with separate idempotency boundaries.

A failure after profile persistence must not save the profile twice or duplicate a cartmutation when retried.

Deferred intent must remain recoverable until successfully claimed/completed or expired.

Do not combine unrelated database aggregates into one distributed transaction.

10. Category Data Requirements

Use the authoritative tenant-owned category model from specifications 018 and 024.

Customer-visible category eligibility requires all of:

category belongs to the trusted tenant;

category lifecycle status is active;

category is customer-visible under business policy; and

category contains at least one active, customer-visible, purchasable product unlessbusiness policy explicitly permits empty categories.

Recommended default: hide empty categories.

Category ordering is deterministic:

display_order ASC, normalized_name ASC, category_id ASC

Categories such as Meat, Groceries, Food, and Pharmacy are examples only. Theymust be created and managed as business data through migrations/seeds or authenticatedcatalog administration—not written into prompts or capability code.

11. Capability Contracts

Reuse browse_catalog and resolve_catalog_browse from specification 018. Add only athin entry capability if needed to combine greeting/profile-safe meaning with the firstauthoritative category page.

11.1 start_customer_shopping

class StartCustomerShoppingArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

It requires no planner-controlled arguments.

Responsibilities:

require trusted tenant context;

use only the safe hydrated fact that onboarding is complete;

fetch the first eligible category page through the catalog browse service;

store the displayed category projection in checkpoint state;

return approved greeting/category fragments and a follow-up when applicable.

It must not read full profile PII, mutate the profile, choose a category, search aproduct, or modify the cart.

If existing orchestration can safely compose the greeting withbrowse_catalog(view="categories") without a new capability, do that instead. Do notduplicate category retrieval policy.

11.2 Category selection

Reuse:

class ResolveCatalogBrowseArguments(BaseModel):
    ordinal: int | None
    navigation: Literal["next", "previous"] | None
    cancelled: bool

Exactly one action is required. When the active browse kind is CATEGORIES, ordinalselects the corresponding category and loads its first current product page.

11.3 Product selection after category

When the active browse kind is PRODUCTS, the ordinal selects only a product from thatdisplayed page through shared product-selection service logic. It must not be interpretedas a category, search-result, pending-add, cart-item, address, or order ordinal.

If selection requires quantity, approved follow-up meaning asks for quantity using onlythe canonical product unit already present in the authoritative product projection.

12. Empty and Changed Catalog Behavior

12.1 No eligible categories

Return approved meaning that no categories are currently available. Do not fabricateoptions. The follow-up may ask for a product name so search_product can check thecurrent catalog, if that can still make progress.

12.2 Selected category has no purchasable products

This may occur when inventory/catalog state changes after display. Return approved emptycategory meaning, clear/refresh stale category-product state, and offer the currentcategory page again.

12.3 Category removed or deactivated after display

Reject the stale ordinal result without existence leakage, refresh categories, and askthe customer to choose from the refreshed list.

12.4 Product changed after display

Reload the product before selection/cart mutation. Current name, status, price, unit,availability, and stock policy are authoritative. Never add based solely on checkpointeddisplay data.

13. Session State and Lifecycle

Reuse CatalogBrowseState from specification 018 and add only the deferred intent statedefined in this specification when required:

class CommerceSession(BaseModel):
    catalog_browse: CatalogBrowseState | None = None
    deferred_customer_intent: DeferredCustomerIntent | None = None

Lifecycle rules:

Category display replaces the previous category browse page.

Category selection replaces it with the selected category's first product page.

Search state and category browse state remain separate ordinal namespaces.

Expired browse state cannot resolve ordinals.

Completed/cancelled/expired deferred intent is cleared.

Profile completion persists independently of checkpoint expiration.

Starting checkout may clear irrelevant browse/deferred state while preserving cart andcheckout authority.

A new conversation for the same stable customer reloads the durable completed profilebut not expired transient browse state.

Recommended configuration:

CUSTOMER_DEFERRED_INTENT_TTL_SECONDS=900
CATALOG_BROWSE_CATEGORY_PAGE_SIZE=10
CATALOG_BROWSE_PRODUCT_PAGE_SIZE=10
CATALOG_BROWSE_STATE_TTL_SECONDS=900
CATALOG_HIDE_EMPTY_CATEGORIES=true

Validate settings at startup and use bounded values.

14. Planner Routing Rules

Add concise capability guidance; do not encode business data in prompts.

Required meaning:

When stable-customer onboarding is incomplete, collect/review/confirm onboardingdetails before a customer-specific cart or checkout mutation.

If a first message also contains a clear supported commerce intent, preserve only itstyped deferred projection for continuation after confirmation.

When onboarding has just completed and no deferred intent exists, executestart_customer_shopping or the equivalent category-browse entry action.

For an onboarded customer's greeting or broad assortment question, show categories.

For an explicit category request, browse that authoritative category.

For an explicit product query, search products directly.

For explicit product, quantity, and purchase intent, use add_product_to_cart.

Resolve an ordinal only through the active displayed workflow state.

Never infer a category or product from assistant text.

Never invent category names, product names, availability, price, quantity, or unit.

One planner decision at a time.

15. Approved Outcomes and Localization

Capabilities provide grounded fragments and follow-ups. Suggested stable IDs include:

customer-welcome
onboarding-details-required
customer-profile-saved
returning-customer-welcome
available-categories
category-products
no-categories-available
category-no-products
stale-category-selection
request-category-selection
request-product-selection

IDs are contracts, not customer-facing English.

Response rules:

Return every approved fragment ID exactly once and in order.

Return the approved follow-up ID exactly when present.

Translate/rephrase surrounding approved meaning into the latest customer language,script, tone, and natural chat style.

Preserve category names, product names, prices, quantities, currencies, units, andordinal numbers exactly as approved.

Prefer list layout for category/product options.

Ask exactly one clear question when a follow-up exists.

Do not add recommendations, products, categories, stock claims, discounts, or nextsteps not present in the approved outcome.

Example Hinglish response:

Welcome back Samad! Aaj kya chahiye?

1. Meat
2. Groceries
3. Food
4. Pharmacy

The exact names and options must come from the execution outcome.

16. Persistence and Transaction Rules

Profile confirmation uses specification 016's transactional and idempotent repositoryboundary.

Category reads are tenant-scoped, bounded, and deterministically ordered.

Product reads always enforce tenant/category relationship in SQL.

Cart mutations use existing active-cart locks and request-id idempotency.

The provider message/request ID remains the trusted runtime idempotency key for channelreplay safety.

Replayed Meta wamid events must not repeat profile confirmation, deferred-intentcontinuation, cart mutation, checkout, or order operations.

Do not store category/product options as durable catalog truth in conversation tables.

Never include full profile PII in generic request-id/idempotency payloads, logs, ormetrics.

No new category table is required if specification 018/024 already created the canonicalschema. If schema work remains, use Alembic and preserve tenant-scoped foreign keys,status, customer visibility, display order, and stable indexes.

17. Concurrency and Retry Safety

Two simultaneous first messages for one customer must not create two profiles.

Concurrent onboarding confirmations return the same completed profile result or a safealready-completed result.

A deferred direct-add is claimed exactly once before mutation and remains recoverableafter retryable failure.

Category/product browsing is read-only and may safely refresh after transient failure.

Product/cart state is revalidated inside the authoritative mutation boundary.

Duplicate webhook deliveries are deduplicated by provider message identity.

A timeout after an ambiguous external send must not rerun the commerce mutation; thepersisted execution/outbound result is reused.

18. Security and Privacy

Verify channel signatures before trusting sender identity.

Never accept tenant ID, customer identity, profile completion, category ID, product ID,or request ID from LLM arguments when trusted context/state owns it.

Do not log raw onboarding messages, phone numbers, addresses, access tokens, appsecrets, webhook signatures, or complete webhook payloads.

Redact PII from errors and operational events.

Customer-visible errors must not reveal whether another customer/category/productexists outside the trusted scope.

Saved details remain unverified until a future phone-ownership milestone.

Apply existing retention/deletion/export policies to saved profiles and conversations.

19. Observability

Use low-cardinality metrics such as:

customer_journey_entries_total{customer_kind,outcome}
customer_onboarding_continuations_total{intent_kind,outcome}
catalog_category_views_total{outcome}
catalog_category_selections_total{outcome}
catalog_product_views_total{outcome}
catalog_browse_expired_references_total{kind}

Rules:

Never label metrics with customer IDs, phone numbers, names, addresses, free text,category names, product names, conversation IDs, or provider message IDs.

Structured logs may include safe internal correlation IDs where policy permits.

Record controlled failure categories, not raw request or response bodies.

20. Testing Requirements

20.1 First-time onboarding

First-time stable customer saying Hi receives one welcome and one combined detailsquestion.

First-time stable customer saying I want 10 kg chicken breast enters onboarding andretains a typed direct-add deferred intent.

Partial/unlabelled/ambiguous details follow specification 016.

No durable profile is written before explicit confirmation.

Confirmation writes one profile and resumes the appropriate continuation.

20.2 Post-onboarding and returning customers

Successful onboarding with no deferred intent returns current categories.

A returning customer's greeting loads the profile and returns current categories.

Returning customer details are not requested again.

Saved phone/address values are not exposed in the greeting.

A deleted/incomplete profile re-enters onboarding safely.

20.3 Intent precedence

What do you have? returns categories.

Show meat products resolves the authoritative category and returns its products.

Do you have Chicken Breast? uses product search, not category browsing.

I want 10 kg Chicken Breast uses direct-add and does not show categories first for anonboarded customer.

Cart, checkout, cancellation, repeat-order, and status intents route to their existingcapabilities.

20.4 Category and product selection

Category ordinal resolves only against the current category page.

Selected category returns only tenant-valid active purchasable products.

Product ordinal resolves only against the current category-product page.

Search, pending-add, cart, address, and order ordinals cannot cross-resolve.

Expired or stale ordinals return a localized clarification/refreshed list.

Deactivated/empty category behavior is deterministic and safe.

20.5 Localization

English, Hindi, Hinglish, and at least one non-Latin script retain the latest customerstyle while preserving approved business values.

All missing/invalid/empty/stale outcomes are localized by the Response Node.

Fragment and follow-up IDs pass strict response validation.

20.6 Persistence, replay, and isolation

Duplicate Meta wamid does not duplicate profile or cart mutations.

Retry after profile persistence resumes rather than recreating the profile.

Deferred direct-add is executed at most once under retry/concurrency.

Tenant A cannot list/select Tenant B categories or products.

A customer cannot supply another channel customer ID to load their profile.

20.7 Failure cases

Database/catalog temporary failure returns a safe retryable outcome.

No categories returns the approved empty-catalog behavior.

Category state changing between display and selection is revalidated.

Invalid quantity/unit/product follows existing direct-add rules without mutation.

Response-generation failure uses deterministic approved fallback content.

21. Acceptance Criteria

This milestone is complete when:

A first-time stable-channel customer is welcomed and asked for all missing deliverydetails together.

Details are reviewed and saved only after explicit confirmation.

After successful onboarding with no stronger deferred intent, current activecategories are displayed from PostgreSQL.

A returning customer's greeting displays current categories without recollectingsaved details.

Selecting a category displays only its current tenant-scoped purchasable products.

Category and product ordinal namespaces cannot be confused with other workflows.

What do you have? displays categories.

Explicit product search and direct product-plus-quantity requests bypass the categorymenu after onboarding.

A valid commerce intent stated before onboarding is resumed safely after confirmationand cannot duplicate side effects on retry.

Every response, including errors and missing-input outcomes, follows the customer'slatest language, script, tone, and chat style using only approved meaning.

Meta webhook replay, concurrent requests, and transient failures do not duplicateprofile, cart, checkout, or order operations.

Automated tests cover routing, persistence, localization, isolation, stale state,concurrency, and replay behavior.

22. Recommended Implementation Order

Audit specifications 016, 017, 018, and 024 plus their implemented models,capabilities, repositories, migrations, and prompts; reuse canonical contracts.

Confirm the canonical category schema supports active status, customer visibility,display order, tenant ownership, and product relationship.

Add safe customer-journey hydration facts and bounded deferred-intent checkpointstate.

Add/extend catalog repository queries for eligible categories and category products.

Implement the customer-entry/category presentation service and capability only if theexisting browse capability cannot compose the required approved outcome cleanly.

Implement post-onboarding continuation with durable profile idempotency and deferredintent claim semantics.

Update planner capability descriptions and routing rules without embedding categorydata.

Add localized approved outcomes and deterministic fallbacks.

Add unit, service, repository, graph, response, concurrency, and Meta replay tests.

Apply any required Alembic migration, run PostgreSQL-backed tests, and complete alive WhatsApp acceptance flow for both a new and returning customer.
Cart Persistence, Short-Term Memory, and Response Localization

Status: Approved for implementationPrerequisite: 003-cart-functionality.mdScope: Persist active carts in PostgreSQL, persist short-term agent state withLangGraph checkpointing, and localize every customer-facing outcome.

1. Goal

The commerce agent must:

retain an active cart across application restarts;

retain short-term conversation context, including recent product results andselected product;

return every customer-facing message in the language, script, tone, and chatstyle of the customer's latest message.

The existing graph remains unchanged:

Planner → Execute → Response → END

No memory, database, or localization graph node is added.

2. Ownership Boundaries

Concern

Owner

Persistence

Products

Commerce domain repository

PostgreSQL

Cart and cart items

Commerce domain repository

PostgreSQL

Orders and payments

Future commerce domain repositories

PostgreSQL

Recent product results and selected product

CommerceSession / graph state

LangGraph Postgres checkpointer

Conversation messages

Graph state

LangGraph Postgres checkpointer

Customer-facing wording

Response Node

Generated per request; not persisted as business state

Rules:

runtime/ owns orchestration only. It contains no SQL and no cart businesslogic.

commerce/ owns cart models, services, and repository interfaces.

infrastructure/ owns PostgreSQL implementations.

The checkpointer persists graph state; it is not a replacement for cart ororder repositories.

A cart repository does not store conversation messages, recent searchresults, or planner decisions.

3. PostgreSQL Cart Schema

3.1 carts

Column

Type

Rule

id

UUID

Primary key.

tenant_id

UUID

Required tenant boundary.

conversation_id

UUID

Required active conversation reference.

status

text

Initially only ACTIVE; future values include CHECKED_OUT and ABANDONED.

created_at

timestamptz

Required.

updated_at

timestamptz

Required.

Constraints and indexes:

UNIQUE (tenant_id, conversation_id, status)
INDEX (tenant_id, conversation_id)

The unique constraint permits one active cart for one tenant and conversation.

3.2 cart_items

Column

Type

Rule

id

UUID

Primary key.

cart_id

UUID

Foreign key to carts.id.

product_id

UUID

Foreign key to products.id.

quantity

numeric

Required; must be greater than zero.

created_at

timestamptz

Required.

updated_at

timestamptz

Required.

Constraints and indexes:

UNIQUE (cart_id, product_id)
CHECK (quantity > 0)
INDEX (cart_id)

For this milestone, adding a product already in the cart replaces its quantity.Quantity accumulation is explicitly deferred.

4. Commerce Repository Contract

Create a commerce-domain CartRepository abstraction. It must expose onlybusiness operations required by cart capabilities:

async def get_or_create_active_cart(
    self,
    tenant_id: UUID,
    conversation_id: UUID,
) -> Cart: ...

async def add_or_replace_item(
    self,
    cart_id: UUID,
    product_id: UUID,
    quantity: Decimal,
) -> Cart: ...

async def get_active_cart(
    self,
    tenant_id: UUID,
    conversation_id: UUID,
) -> Cart | None: ...

async def remove_item_by_ordinal(
    self,
    cart_id: UUID,
    ordinal: int,
) -> Cart: ...

PostgresCartRepository implements this interface using asyncpg and isinjected into CartService through the application container.

The repository returns domain models, never database rows or dictionaries.

5. Capability Behaviour

5.1 add_to_cart

Validate quantity deterministically with Pydantic.

Resolve the product from selected_product, or from a valid recent-resultordinal when the capability contract supports direct selection plus quantity.

Use CartService and CartRepository to create or find the active cart andadd/replace the item in one database transaction.

Return a GeneratedExecutionOutcome with approved business values.

Update CommerceSession.cart_items from the returned domain cart.

5.2 view_cart

Read the active cart from CartRepository.

Return an empty-cart generated outcome if no active cart or no items exist.

Otherwise, return ordered item fragments and 1-based cart ordinals.

Refresh CommerceSession.cart_items from the persisted cart.

5.3 remove_from_cart

Validate its 1-based cart ordinal deterministically.

Load and mutate the active cart in a transaction.

Return a generated confirmation or a generated invalid-ordinal outcome.

Refresh CommerceSession.cart_items from the persisted cart.

Capabilities do not construct SQL, translate messages, or write checkpoint datadirectly.

6. Transaction and Consistency Rules

get_or_create_active_cart and item upsert must be safe under concurrentrequests for the same tenant and conversation.

Use a transaction for cart creation and item replacement.

Rely on database uniqueness constraints; do not use only in-memory checks.

Persist the cart before returning the success outcome.

If persistence fails, do not return an “added to cart” success message.

The database cart is authoritative. CommerceSession.cart_items is aconvenient snapshot for planning and response context.

7. Short-Term Memory Persistence

Use LangGraph checkpointing for short-term state, with conversation_id mappedto the graph thread_id.

Persist through the checkpointer:

conversation messages;

recent_product_results in their original order;

selected_product;

CommerceSession.cart_items snapshot;

planner and execution graph state needed to resume a conversation.

Use MemorySaver only in local development. Use a PostgreSQL-backed LangGraphcheckpointer in production.

Do not add a separate custom memory table for this state. Do not overwrite acheckpointed session with an empty inbound session; when no new session isprovided, resume the checkpointed session.

8. Response Localization

8.1 Rule

Every customer-facing outcome must pass through the Response Node before beingreturned to the customer.

This includes success, not-found, missing-input, invalid-input, and empty-cartoutcomes, such as:

missing-selected-product;

invalid-cart-quantity;

no-recent-results;

invalid-ordinal;

cart-empty;

cart add, view, and remove confirmations.

The capability supplies approved canonical meaning. The Response Node adaptsonly the surrounding language and style.

8.2 Protected Values

The Response Node must preserve exactly:

product names;

prices and currency;

quantities and units;

availability;

displayed option numbers;

fragment IDs and follow-up IDs.

It may translate or rephrase only explanatory wording and follow-up questions.

Examples:

Latest customer style

Approved meaning

Valid response style

I want chicken breast

selected product; request quantity

Chicken Breast selected. How much would you like to order?

chicken breast dedo

selected product; request quantity

Chicken Breast select ho gaya. Kitni quantity chahiye?

मुझे चिकन ब्रेस्ट चाहिए

selected product; request quantity

Chicken Breast select हो गया। कितनी quantity चाहिए?

8.3 Fixed Outcomes

FixedExecutionOutcome currently bypasses response generation. It thereforecannot adapt to the customer's language.

For this milestone, every customer-facing fixed message must either:

be represented as a GeneratedExecutionOutcome and pass through theResponse Node; or

be passed through the Response Node using the same approved-fragmentcomposition path.

The first option is preferred for normal commerce responses. Fixed outcomesremain appropriate only for non-customer-facing internal control paths.

9. Acceptance Criteria

Add-to-cart creates or updates a PostgreSQL cart and item before returningsuccess.

Restarting the application does not lose an active cart.

view_cart reads the persisted cart, not only an in-memory session copy.

remove_from_cart persists the removal transactionally.

A resumed conversation_id restores messages, recent product results, andselected product through the PostgreSQL LangGraph checkpointer.

No custom short-memory table duplicates checkpointed graph state.

Every success, missing-input, invalid-input, and not-found response iscomposed by the Response Node.

A Roman-script Hinglish customer receives Roman-script Hinglish surroundingwording; product names and numeric business values remain unchanged.

No SQL is added to runtime/, planner, handlers, or capabilities.

The graph remains Planner → Execute → Response → END.

10. Required Tests

Cart repository creates one active cart per tenant and conversation.

Cart repository replaces an existing item quantity.

Cart repository rejects non-positive quantities through database constraints.

Cart capabilities return no success outcome when repository persistence fails.

Persisted cart is available after container restart and session reload.

Checkpoint resume restores recent results and selected product.

Generated missing-input and invalid-input outcomes reach the Response Node.

Response composition preserves protected business values while matching English,Roman-script Hinglish, and Devanagari Hindi customer styles.

Fixed customer-facing outcomes do not bypass localization.
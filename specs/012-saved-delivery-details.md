Saved Delivery Details Specification

1. Purpose

Allow a returning customer to reuse a saved name, phone number, and delivery addresswithout introducing OTP, passwords, login sessions, or claims of verified identity.

Saved details are a checkout convenience feature. They are resolved only from a trustedchannel identity supplied by the application boundary. Guest checkout must continue towork when no stable channel identity exists or when the customer declines to save data.

2. Frozen Architecture

The graph remains:

Planner -> Execute -> Response -> END

Do not add a LangGraph node.

The planner selects one action and never reads or writes the database directly.

Capabilities validate typed arguments and delegate business operations.

Commerce services own consent and delivery-detail business rules.

Repository implementations own PostgreSQL queries and transactions.

PostgreSQL is authoritative for saved customer details, carts, orders, and inventory.

LangGraph checkpointing stores conversation messages and short-termCommerceSession state only.

Trusted tenant_id, conversation_id, channel, and channel customer identifier comefrom runtime request context, never from LLM capability arguments.

The Response Node localizes approved meaning into the latest customer's language,script, tone, and chat style.

3. Security Boundary and Terminology

This milestone does not authenticate or verify a person.

Use these terms:

Trusted channel identity: a stable identifier asserted by a configured ingressadapter, such as a WhatsApp sender identifier or an application-issued developmentcustomer identifier.

Guest: a conversation without a stable trusted channel identity.

Saved delivery profile: reusable delivery data associated with a trusted channelidentity. It is not a verified customer account.

Do not call a profile authenticated, verified, logged in, or account-owned.

For REST development, the application may accept a development customer identifier onlythrough trusted server configuration or an explicitly development-only request path. Aproduction client must not be able to impersonate another customer by freely supplyingan arbitrary identifier.

Saved details must not become an authorization mechanism for order history, payment,refund, staff actions, or other sensitive operations.

4. Scope

4.1 Included

Optional saved delivery profile containing a preferred customer name and phone.

Multiple saved delivery addresses.

Add, list, select, update, delete, and set a default address.

Dedicated saved-address ordinal namespace.

Explicit consent before first save or overwrite.

Guest checkout and one-time delivery details.

Use selected saved details to populate checkpointed checkout state.

Tenant isolation and trusted channel identity resolution.

Localized approved outcomes and deterministic fallbacks.

Alembic migrations, repository/service contracts, and automated tests.

4.2 Explicitly excluded

OTP and phone-number verification.

Passwords, login sessions, access tokens, social login, and account recovery.

Claims that a phone number or identity is verified.

Payment methods or payment credentials.

Automatic address validation, geocoding, or delivery-zone calculation.

Automatically saving checkout details without consent.

Automatically overwriting existing saved details.

Sharing a saved profile across tenants.

Using LLM-extracted identity as trusted identity.

5. Trusted Runtime Context

Extend the trusted invocation context outside LLM-visible arguments:

class CustomerChannelContext(BaseModel):
    tenant_id: UUID
    conversation_id: UUID
    channel: ChannelName
    channel_customer_id: str | None

Rules:

channel_customer_id is None means guest mode.

Channel adapters normalize identifiers before invoking the runtime.

The planner may see only safe state such as saved profile available; it does notneed the raw channel identifier.

No capability schema may accept tenant_id, conversation_id, channel, orchannel_customer_id from the LLM.

Services and repositories receive trusted context through dependency-injectedcapability input or an equivalent application-owned execution context.

6. Domain Models

6.1 Saved delivery profile

class SavedDeliveryProfile(BaseModel):
    id: UUID
    tenant_id: UUID
    channel: ChannelName
    channel_customer_id: str
    customer_name: str | None
    phone_number: str | None
    created_at: datetime
    updated_at: datetime

The phone number is customer-provided and unverified. Continue using the existing phoneformat validation policy, but successful formatting validation must never be describedas identity verification.

6.2 Saved delivery address

class SavedDeliveryAddress(BaseModel):
    id: UUID
    profile_id: UUID
    label: str
    delivery_address: str
    is_default: bool
    version: int
    created_at: datetime
    updated_at: datetime

Rules:

label and delivery_address are non-empty after trimming.

Labels are customer-defined names such as Home or Office; they do not proveaddress ownership.

At most one non-deleted default address exists per profile.

version supports safe concurrent update and delete operations.

Address identity is never supplied as arbitrary LLM text when an ordinal can resolveit from current structured session results.

6.3 Session projection

Add only a short-lived, customer-safe projection to CommerceSession:

class SavedAddressOption(BaseModel):
    address_id: UUID
    label: str
    delivery_address: str
    is_default: bool
    version: int


class CommerceSession(BaseModel):
    # existing fields
    recent_saved_addresses: tuple[SavedAddressOption, ...] = ()

Do not store the full durable profile in checkpoint state. Clear or replacerecent_saved_addresses whenever a new list is loaded or an address mutation succeeds.

7. PostgreSQL Schema

Create application-owned tables through Alembic.

7.1 saved_delivery_profiles

Column

Type

Rule

id

UUID

Primary key

tenant_id

UUID

Required trusted tenant

channel

text

Required normalized channel

channel_customer_id

text

Required stable channel subject

customer_name

text

Nullable

phone_number

text

Nullable, unverified

created_at

timestamptz

Required

updated_at

timestamptz

Required

Required uniqueness:

UNIQUE (tenant_id, channel, channel_customer_id)

7.2 saved_delivery_addresses

Column

Type

Rule

id

UUID

Primary key

profile_id

UUID

Required foreign key

label

text

Required, non-empty

delivery_address

text

Required, non-empty

is_default

boolean

Required, default false

version

integer

Required, starts at 1

created_at

timestamptz

Required

updated_at

timestamptz

Required

Add:

INDEX (profile_id, created_at, id)
UNIQUE INDEX one_default_address_per_profile
    ON saved_delivery_addresses (profile_id)
    WHERE is_default = TRUE

Use the project's established soft-delete policy if one already exists. Otherwise usehard deletion for addresses in this milestone and document that deletion removes thesaved convenience record, not historical order snapshots.

Historical orders retain immutable delivery snapshots and must not reference mutablesaved-address text as their only source.

8. Repository Contracts

Create a commerce-domain SavedDeliveryDetailsRepository interface and a PostgreSQLimplementation.

Required operations, adapted to existing naming conventions:

async def get_profile(
    tenant_id: UUID,
    channel: ChannelName,
    channel_customer_id: str,
) -> SavedDeliveryProfile | None: ...

async def save_profile_details(
    tenant_id: UUID,
    channel: ChannelName,
    channel_customer_id: str,
    customer_name: str | None,
    phone_number: str | None,
) -> SavedDeliveryProfile: ...

async def list_addresses(
    tenant_id: UUID,
    profile_id: UUID,
) -> tuple[SavedDeliveryAddress, ...]: ...

async def add_address(...) -> SavedDeliveryAddress: ...
async def update_address(...) -> SavedDeliveryAddress: ...
async def delete_address(...) -> None: ...
async def set_default_address(...) -> SavedDeliveryAddress: ...

Every address query must join or verify its profile under the same trusted tenant.Never rely on address UUID uniqueness alone for tenant isolation.

update_address and delete_address require the expected version. A stale versionreturns a typed business conflict rather than overwriting concurrent changes.

Setting a default address must run in one transaction:

lock the tenant-scoped profile/address set;

verify the target address belongs to the profile;

clear the previous default;

set the target default; and

commit.

9. Service Rules

Add SavedDeliveryDetailsService with these invariants:

Reject durable save/mutation operations in guest mode.

Validate name and address as non-empty normalized text.

Validate phone format with the existing policy while marking it unverified.

Require explicit customer consent before first persistence.

Require explicit confirmation before overwriting a different stored name, phone, oraddress value.

Never derive consent from previously agreeing to place an order.

Never use an order confirmation as consent to save details.

Do not copy saved data into checkout until the customer selects or explicitly acceptsit.

Existing order snapshots never change when a saved profile changes.

If the default address is deleted, leave no default unless the customer explicitlyselects another one. Do not guess a replacement.

10. Capability Contracts

Register the following capabilities using the project's existing metadata and outcomecontracts.

10.1 list_saved_addresses

Requires no LLM arguments. It resolves trusted channel context, loads the profile andaddresses, and replaces recent_saved_addresses.

Outcomes:

guest mode: explain that saved addresses are unavailable while allowing one-timecheckout details;

no profile/address: explain no saved addresses exist;

addresses found: return ordered item fragments with dedicated 1-based ordinals.

Use deterministic ordering: default first, then creation time, then ID.

10.2 select_saved_address

class SelectSavedAddressArguments(BaseModel):
    ordinal: int = Field(strict=True, ge=1)

Resolve only against recent_saved_addresses. Reload the selected address using trustedtenant/profile identity before applying it. Copy the exact current address intocheckpointed CheckoutState.delivery_address.

If a saved profile contains a name or phone and checkout is missing that field, presentit for explicit use; do not silently overwrite already collected checkout values.

10.3 save_delivery_details

class SaveDeliveryDetailsArguments(BaseModel):
    customer_name: NonEmptyText | None = None
    phone_number: NonEmptyText | None = None
    address_label: NonEmptyText | None = None
    delivery_address: NonEmptyText | None = None
    set_as_default: bool = False
    consent: Literal[True]

The planner may set consent=True only from the latest customer's explicit agreementto save. The capability must not interpret order confirmation as saving consent.

If stored values would be overwritten, return an approved comparison and ask forexplicit overwrite confirmation rather than mutating immediately.

10.4 update_saved_address

class UpdateSavedAddressArguments(BaseModel):
    ordinal: int = Field(strict=True, ge=1)
    label: NonEmptyText | None = None
    delivery_address: NonEmptyText | None = None

Resolve the ordinal from recent_saved_addresses, require at least one changed value,and use the stored version for optimistic concurrency. On success, refresh or clear therecent list so a stale ordinal cannot be reused.

10.5 delete_saved_address

class DeleteSavedAddressArguments(BaseModel):
    ordinal: int = Field(strict=True, ge=1)

Deletion requires explicit customer intent naming a valid recent saved-address ordinal.After success, refresh or clear the list. It must not modify historical orders or thecurrent cart.

10.6 set_default_address

class SetDefaultAddressArguments(BaseModel):
    ordinal: int = Field(strict=True, ge=1)

Resolve only against recent saved addresses and update the default transactionally.Repeatedly selecting the existing default is idempotent.

11. Checkout Integration

At delivery-detail collection:

If there is no trusted channel identity, continue the existing guest flow.

If a profile may exist, the planner may execute list_saved_addresses before askingthe customer to type an address.

The customer may select a saved address or provide a one-time address.

A selected address is copied into CheckoutState as a value snapshot.

Checkout review displays the exact chosen name, phone, and address.

The customer must explicitly confirm the COD order as before.

Order creation stores immutable delivery snapshots.

Changing or deleting a saved address after it is copied into checkout does not silentlychange checkout. The checkout review remains the authority for what the customer isabout to confirm. If the customer explicitly selects a different saved address, producea fresh review and require confirmation again.

Cart mutations continue to invalidate checkout state under the existing cart-editingrules.

12. Planner Routing Rules

When the customer asks to see saved addresses, execute list_saved_addresses.

A valid ordinal referring to the most recent saved-address list executesselect_saved_address when the customer is choosing a checkout address.

Never interpret a saved-address ordinal as a product-result, cart-item, stock-recovery,or order ordinal.

A request to save current delivery details must first have explicit save consent.

If consent is missing, ask exactly one consent question; do not persist anything.

Explicit add/update/delete/default-address intent routes to its dedicated capability.

Guest mode must not cause repeated requests to create an account or verify a phone.

A one-time address continues through existing collect_delivery_details.

Never infer trusted customer identity from a name, phone number, address, or assistantmessage.

Never claim a phone number is verified.

One decision per planner turn remains mandatory.

These rules apply to all languages, scripts, informal spellings, transliteration, andmixed-language chat styles.

13. Address Ordinal Namespace

Saved-address ordinals are valid only when recent_saved_addresses contains the listmost recently shown to the customer.

Ordinals are 1-based integers.

The list is replaced, never merged, after a new list operation.

Mutations clear or refresh the list.

An ordinal from assistant text alone is insufficient.

If no recent saved-address list exists, ask the customer to list or clarify addresses.

An ordinal cannot be reused across product results, cart items, orders, order items,stock shortages, or saved addresses.

14. Approved Outcomes and Response Localization

Recommended stable IDs:

Situation

Fragment ID

Follow-up ID

Saved addresses listed

saved-addresses plus item IDs

Optional select-saved-address

No saved addresses

no-saved-addresses

provide-delivery-address

Guest mode

saved-addresses-unavailable-for-guest

provide-delivery-address

Address selected

saved-address-selected

Existing next checkout detail/review ID

Save consent required

delivery-details-not-saved

confirm-save-delivery-details

Details saved

delivery-details-saved

None or approved checkout continuation

Overwrite required

saved-details-differ

confirm-saved-details-overwrite

Address updated

saved-address-updated

None

Address deleted

saved-address-deleted

None

Default changed

default-address-updated

None

Stale address

saved-address-changed

review-saved-addresses

Response rules:

Use only approved fragments, follow-up, and options as source meaning.

Match the latest customer's language, script, tone, and chat style.

Preserve exact customer-provided names, phone numbers, address labels, addresses, andoption numbers when approved for display.

Translate only surrounding explanatory text.

Prefer list layout for multiple addresses.

Ask exactly one clear question when a follow-up exists.

Never add claims of verification, ownership, serviceability, or successful delivery.

Deterministic fallback must preserve every approved fragment ID in order.

15. Privacy and Logging

Treat names, phone numbers, addresses, and channel customer identifiers as personaldata.

Do not include raw phone numbers, full addresses, or channel identifiers in routinelogs, metrics, exception messages, planner debug output, or tracing attributes.

Mask phone numbers when listing reusable profile details unless the customer is in anactive checkout review where the exact approved value is required.

Avoid exposing full saved addresses before trusted channel context has resolved theprofile.

Define retention and deletion policy before production launch.

Deleting a saved profile/address does not erase legally required historical ordersnapshots; document this distinction in customer-facing privacy behavior.

Never store payment credentials in these tables.

16. Error and Concurrency Handling

Missing trusted identity: return guest-safe behavior, not an internal error.

Missing/deleted selected address: clear the recent list and request a fresh list.

Stale address version: apply no mutation and request review.

Duplicate concurrent profile creation: rely on the unique identity constraint, loadthe winning row, and continue safely.

Concurrent default changes: serialize within the profile transaction and preserve onedefault.

Invalid phone format: preserve existing stored and checkout values.

Partial multi-field validation failure: apply no durable mutation.

Database failure: roll back and return a customer-safe temporary failure.

Response composition failure: use deterministic approved fallback.

Do not introduce a broad retry framework in this milestone. Reuse an established scopeddatabase retry policy only where its documented SQLSTATE and idempotency guaranteesapply.

17. Testing Requirements

17.1 Domain and service tests

Guest mode cannot persist saved details and can still complete checkout.

Explicit consent saves supplied valid details.

Order confirmation alone does not imply save consent.

Existing differing values require overwrite confirmation.

Invalid phone or empty address causes no partial update.

Selecting an address copies a snapshot into checkout.

Updating saved data does not mutate historical orders.

Deleting the default leaves no default until explicitly changed.

17.2 Repository tests

Profile identity is unique by tenant, channel, and channel customer identifier.

The same channel customer identifier can exist independently in two tenants.

Every address operation verifies the tenant-scoped profile.

Optimistic versions prevent stale update and delete.

Concurrent default changes leave exactly one default.

Duplicate profile creation resolves without duplicate rows.

17.3 Planner tests

List/select/save/update/delete/default intents route correctly.

Explicit consent is required before save_delivery_details.

Saved-address ordinals never cross other ordinal namespaces.

Guest checkout does not route into authentication or OTP.

Names, phone numbers, and addresses are never treated as trusted identity.

English, Hindi, Romanized Hindi, and mixed-language requests route consistently.

17.4 Integration tests

A returning trusted channel customer lists and selects a saved address, reviewscheckout, and confirms one COD order with an immutable address snapshot.

A guest provides one-time details and completes the same COD flow without databaseprofile rows.

A customer declines saving; no profile or address is written.

An address update followed by checkout selection uses the new snapshot.

A saved-address change after checkout selection does not silently alter the pendingcheckout review.

Cross-tenant identity, profile, and address access is rejected without data leakage.

Response and deterministic fallback remain grounded and localized.

18. Definition of Done

This milestone is complete when:

trusted channel identity is injected outside LLM arguments;

guest checkout remains fully functional;

profiles and multiple addresses persist through Alembic-managed tables;

saving and overwriting require explicit consent;

saved addresses have a dedicated, safe ordinal namespace;

checkout uses copied delivery snapshots and still requires explicit COD confirmation;

no response claims authentication or phone verification;

tenant isolation, privacy, optimistic concurrency, and default uniqueness are tested;

all generated and fallback responses remain grounded and localized; and

the graph remains Planner -> Execute -> Response -> END.

19. Deferred Next Milestones

Online payment lifecycle and webhook reconciliation.

Customer notifications for order confirmation, dispatch, delivery, and cancellation.

OTP-based customer authentication and verified phone ownership.

Authenticated staff fulfilment APIs.

Production privacy controls, security hardening, rate limiting, observability, anddeployment.
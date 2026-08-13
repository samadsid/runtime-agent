Customer Onboarding and Profile Memory Specification

1. Purpose

Introduce a first-visit onboarding flow that welcomes a customer, requests their name,phone number, and delivery address together, and saves the supplied details as along-term delivery profile for later conversations and checkout.

This milestone extends 012-saved-delivery-details.md. It must reuse the existingsaved-delivery profile, address, trusted channel identity, consent, service, repository,tenant-isolation, and checkout-reuse rules. It must not introduce a second customerprofile table or a competing source of delivery data.

Because OTP authentication is deferred, every stored phone number remains unverified.The saved profile is a convenience record, not proof of identity or account ownership.

2. Goals

Recognize whether a stable channel customer has completed onboarding.

Welcome first-time customers in their latest language, script, tone, and chat style.

Request all currently missing onboarding fields in one customer-facing question.

Validate and persist supplied profile details through typed capabilities and domainservices.

Reuse saved profile data in later conversations without repeatedly collecting it.

Preserve guest commerce behavior when no stable trusted channel identity exists.

Avoid adding LangGraph nodes or moving business logic into prompts or channel routes.

Keep personal data out of planner arguments, logs, metrics, and untrusted browseridentity claims.

3. Non-goals

OTP verification or verified phone ownership.

Passwords, login sessions, access tokens, account recovery, or social login.

Staff access to customer profiles.

Marketing consent or promotional messaging.

Payment-method storage.

Address geocoding, delivery-zone validation, or proof of address.

Automatic customer deduplication across channels or phone numbers.

Treating a web development header as production authentication.

Blocking all product browsing for guest customers.

Changing the frozen commerce graph.

4. Frozen Architecture

The graph remains:

Planner -> Execute -> Response -> END

The invocation flow becomes:

Trusted channel adapter
    -> resolve channel customer context
    -> hydrate safe onboarding/profile projection
    -> Planner
    -> onboarding or commerce capability
    -> service
    -> PostgreSQL repository
    -> Response

Rules:

Do not add an onboarding LangGraph node.

Do not read or write profiles directly from the planner, prompts, response generator,REST route, Twilio route, or React frontend.

Trusted tenant_id, channel, channel_customer_id, and conversation_id come fromapplication context, never from LLM arguments.

The planner selects one action per graph execution.

Capabilities validate typed input and produce approved outcomes.

Domain services own consent, normalization, completion, and overwrite rules.

PostgreSQL is authoritative for saved profiles and addresses.

LangGraph checkpoint state contains only minimal short-term onboarding progress and asafe profile projection.

The Response Node localizes approved meaning and never changes profile data.

5. Identity and Trust Boundary

Use the existing CustomerChannelContext:

class CustomerChannelContext(BaseModel):
    tenant_id: UUID
    conversation_id: UUID
    channel: ChannelName
    channel_customer_id: str | None
    request_id: str

Definitions:

Stable channel customer: a customer for whom the application boundary supplies astable channel identifier.

Guest: channel_customer_id is None.

Saved delivery profile: reusable, customer-provided delivery information linkedto a stable channel identifier.

Verified phone: a future state requiring OTP or another approved verificationmechanism; it is not produced by this milestone.

Channel rules:

A signed Twilio webhook may supply a stable WhatsApp sender identifier, but this doesnot make the saved profile an authenticated account.

The REST development adapter may supply an environment-gated development customeridentifier.

The normal production web client must not be able to choose an arbitrary customer IDand load another profile.

Until authenticated web identity exists, web profile memory is development-only ordevice-scoped convenience and must be described accordingly.

Never match or merge profiles solely because two profiles contain the same phonenumber.

6. Customer Experience

6.1 First visit with stable identity

When no completed saved profile exists, the first response must:

greet the customer;

explain that the details are needed for ordering and delivery;

disclose that the details will be saved for future orders; and

ask for name, phone number, and complete delivery address together as exactly oneclear question.

Example approved meaning:

Welcome! To prepare deliveries and save time on future orders, please share the name,
phone number, and complete delivery address you would like me to save.

The Response Node may naturally localize this. For Hinglish:

Hi! Order aur delivery ke liye apna naam, phone number aur complete address share kar
do. Main in details ko future orders ke liye save karunga—kya details use karni hain?

The response must not call the phone number verified.

6.2 Customer supplies all fields

Example input:

Mera naam Samad hai, number 9560717170 hai aur address B-68, 2nd Floor, DDA Colony,
New Zafrabad, Delhi hai.

The planner executes collect_customer_onboarding_details with only the threeconfidently extracted profile values. The capability validates them and stores them asa checkpointed proposal; it does not write long-term profile data yet.

The customer must receive a review containing the proposed fields:

Name: Samad
Phone: 9560717170
Address: B-68, 2nd Floor, DDA Colony, New Zafrabad, Delhi

Are these details correct?

Only an explicit confirmation routes to confirm_customer_onboarding, which persiststhe proposal under trusted runtime context.

Successful approved meaning:

Your delivery details have been saved for future orders.

The follow-up may ask what the customer would like to order. It must not claim that thephone, address, or identity was verified.

6.3 Partial details

If the customer supplies only some fields:

validate and retain the valid supplied values in checkpointed pending state;

do not persist a completed durable profile yet;

request every remaining missing field together in exactly one follow-up question;

do not ask for already valid pending values again; and

do not split name, phone, and address into three mandatory turns.

Example:

USER: Samad, 9560717170
ASSISTANT: Thanks—future delivery ke liye complete address kya save karu?

6.4 Invalid field

Preserve other valid pending fields.

Identify only the invalid field's approved meaning.

Ask one question covering the invalid field and any other still-missing fields.

A syntactically valid phone remains phone_verified = false.

6.5 Unlabelled and ambiguous details

Customers may provide fields in any order and without labels:

b-68 2nd Floor dda colony samad 9560717170

When the meaning is sufficiently clear, the proposed extraction is:

{
  "customer_name": "samad",
  "phone_number": "9560717170",
  "delivery_address": "b-68 2nd Floor dda colony"
}

Extraction rules:

Extract only values present in the latest customer message or already validatedpending state.

Fields may appear in any order and may use labels, natural sentences, or informalchat spelling.

Recognize a valid phone-number sequence separately from surrounding text.

Treat house numbers, floors, streets, roads, colonies, sectors, cities, states,landmarks, and postal codes as address evidence.

Do not include a clearly distinguished person's name in the address.

Preserve the customer's spelling and script apart from established whitespace andphone normalization.

Never invent a value.

If name and address boundaries cannot be determined confidently, omit the ambiguousfield instead of guessing and ask one clarification question for all unresolvedfields.

For example, this is genuinely ambiguous:

B-68 Samad Colony 9560717170

Samad may be the customer name or part of Samad Colony. The planner must not guess.It may safely retain the phone, retain only address text it can identify withoutsplitting uncertain tokens, and request the customer's name/address in a labelled orotherwise unambiguous form.

The onboarding request should encourage, but not require, a labelled response:

Name:
Phone:
Complete address:

Natural unlabelled replies remain supported. Labels are a usability aid, not a new APIrequirement.

6.6 Review and correction

Once all three proposed fields are valid, the system moves to REVIEWING_DETAILS andshows each field separately before durable persistence.

Rules:

Ask exactly one confirmation question.

Do not describe the details as saved before confirmation succeeds.

If the customer confirms, execute confirm_customer_onboarding with no PIIarguments; use only the checkpointed proposal and trusted context.

If the customer corrects one or more fields, executecollect_customer_onboarding_details with only the newly supplied corrections,retain other proposed fields, and display a new review.

If the customer rejects the review without supplying a correction, ask which fieldsshould be corrected.

A correction must never be interpreted as order confirmation, cart confirmation, ormarketing consent.

6.7 Decline or skip

The customer may decline, say skip, or continue with a product request.

Do not create a durable profile without explicit confirmation of the displayeddelivery-detail review.

Mark onboarding as skipped for the current conversation only.

Allow catalog browsing, product selection, and cart operations.

Require one-time delivery details before order confirmation under the existingcheckout rules.

A future conversation may offer onboarding again unless an explicit durable privacypreference is later introduced.

Onboarding must not become a forced PII gate before a customer can inspect products orprices.

6.8 Returning customer

When a completed profile is found:

do not ask for the same three details again;

expose only a safe projection such as preferred name and profile availability to theplanner;

greet naturally using the saved preferred name when appropriate;

never include the full phone or address in the planner prompt merely to greet; and

apply the saved details to checkout only under the reuse/acceptance rules frozen in012-saved-delivery-details.md.

Example:

Welcome back, Samad! What would you like to order today?

7. Consent Rule

The first onboarding request must clearly state that the supplied details are intendedto be saved for future orders. Durable consent is completed only when the customerexplicitly confirms the displayed review. Supplying extractable text alone does notauthorize persistence.

Record:

consent purpose/version;

consent timestamp;

source channel; and

request ID used for idempotency.

Rules:

Silence, unrelated commerce text, a greeting, cart confirmation, checkoutconfirmation, or order confirmation is not consent to save.

A customer correction is not confirmation; display the corrected review again.

Do not infer marketing consent from profile-storage consent.

Do not overwrite different existing saved values through onboarding; use theexisting explicit profile-update confirmation flow.

If legal or product policy later requires a separate confirmation turn, change theconsent policy without weakening the persistence boundary.

8. Durable Domain Model

Reuse SavedDeliveryProfile and SavedDeliveryAddress from specification 012.

Extend the profile model as needed:

class SavedDeliveryProfile(BaseModel):
    id: UUID
    tenant_id: UUID
    channel: ChannelName
    channel_customer_id: str
    customer_name: str | None
    phone_number: str | None
    phone_verified: bool = False
    onboarding_status: OnboardingStatus
    profile_consent_version: str | None
    profile_consented_at: datetime | None
    created_at: datetime
    updated_at: datetime

class OnboardingStatus(str, Enum):
    INCOMPLETE = "INCOMPLETE"
    COMPLETED = "COMPLETED"

The delivery address remains in saved_delivery_addresses, not duplicated as a mutablecolumn on the profile. Initial onboarding creates one default address with a stablesystem label such as Home only if the existing domain permits system-assigned labels;otherwise use a neutral label such as Primary and localize only its presentation.

Completion invariant:

customer_name present
AND phone_number present
AND at least one active saved address present
AND profile consent recorded

phone_verified must always be false in this milestone.

9. PostgreSQL Migration

Use Alembic to extend the existing saved_delivery_profiles table rather than creatinga new customer table.

Add, where not already present:

Column

Type

Rule

phone_verified

boolean

Not null, default false

onboarding_status

text

Not null, default INCOMPLETE

profile_consent_version

text

Nullable until completed

profile_consented_at

timestamptz

Nullable until completed

onboarding_request_id

text

Nullable, idempotency/audit reference

Preserve existing uniqueness:

UNIQUE (tenant_id, channel, channel_customer_id)

Migration rules:

Backfill phone_verified = FALSE for existing profiles.

Mark an existing profile COMPLETED only when it already satisfies the completioninvariant and its existing consent record is sufficient under project policy.

Otherwise leave it INCOMPLETE and collect only missing data later.

Do not overwrite existing names, phone numbers, or addresses during migration.

Do not log migrated PII.

Provide a reversible downgrade consistent with the project's migration policy.

10. Short-Term Onboarding State

Add minimal checkpointed state:

class OnboardingStage(str, Enum):
    NOT_REQUIRED = "NOT_REQUIRED"
    NOT_STARTED = "NOT_STARTED"
    COLLECTING_DETAILS = "COLLECTING_DETAILS"
    REVIEWING_DETAILS = "REVIEWING_DETAILS"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"


class CustomerOnboardingState(BaseModel):
    stage: OnboardingStage = OnboardingStage.NOT_STARTED
    pending_customer_name: str | None = None
    pending_phone_number: str | None = None
    pending_delivery_address: str | None = None

Rules:

Do not store trusted tenant/channel identifiers inside LLM arguments.

Pending state may exist only until completion, skip, expiration, or conversationreset.

Pending values in REVIEWING_DETAILS are an uncommitted proposal and must not betreated as durable long-term memory.

Clear pending values immediately after successful durable save.

Do not copy a full durable profile or address list into onboarding checkpoint state.

Persist durable completion in PostgreSQL so a new conversation can recognize thereturning customer.

Do not rely only on checkpoint state to determine whether onboarding is completed.

11. Profile Hydration

Before planner invocation, the application runtime may load the profile using trustedchannel context and expose this safe projection:

class CustomerProfileProjection(BaseModel):
    profile_available: bool = False
    onboarding_completed: bool = False
    preferred_name: str | None = None
    missing_fields: tuple[ProfileField, ...] = ()

Do not expose raw phone number or full address in ordinary planner prompts.

Hydration rules:

Guest context produces profile_available = false without a repository lookup thatinvents identity.

Tenant, channel, and channel customer ID scope every lookup.

Database unavailability must not silently create a second profile.

Hydration failure produces a safe temporary response or guest fallback according toestablished runtime policy.

A safe projection is refreshed after every successful profile mutation.

12. Capabilities

12.1 start_customer_onboarding

Arguments: none.

The capability:

resolves trusted channel context;

checks durable profile completion;

sets onboarding stage to COLLECTING_DETAILS when required;

requests all missing fields together;

includes the save-purpose disclosure; and

returns a localized-ready approved outcome.

Outcomes:

already completed: no mutation; return a returning-customer greeting/follow-up;

guest: explain that details can be supplied for checkout but cannot be safely reusedas a durable channel profile;

incomplete: request every missing field together;

temporary repository failure: safe retryable failure without collecting or losingpersonal data.

12.2 collect_customer_onboarding_details

class CollectCustomerOnboardingDetailsArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_name: NonEmptyText | None = None
    phone_number: NonEmptyText | None = None
    delivery_address: NonEmptyText | None = None

Rules:

All fields are optional in one invocation so natural partial replies are supported.

Reject explicit null values when supplied.

Normalize non-empty text.

Validate the phone through the existing PhoneValidationPolicy.

Merge supplied valid values with pending onboarding state.

If fields remain missing, request all remaining fields together and do not persist acompleted profile.

If every field is valid, move to REVIEWING_DETAILS, display all three proposedvalues separately, and ask exactly one confirmation question.

Do not persist profile, consent, or address data from this capability.

Never accept tenant, channel, channel customer ID, consent timestamp, verified flag,or database IDs from the planner.

Never overwrite a different completed profile through this capability.

12.3 confirm_customer_onboarding

Arguments: none.

The capability:

requires REVIEWING_DETAILS state;

requires all three validated pending values;

interprets only an explicit customer confirmation selected by the planner;

obtains consent timestamp/version and request ID from trusted application context;

persists profile, unverified phone, consent, and initial default address atomically;

clears pending PII after successful commit; and

moves the onboarding stage to COMPLETED.

It must fail safely without persistence when review state is missing, incomplete, stale,or expired. The LLM must never pass the reviewed PII back as capability arguments.

12.4 skip_customer_onboarding

Arguments: none.

The capability:

sets checkpoint onboarding stage to SKIPPED;

clears pending PII;

performs no durable profile mutation;

allows normal commerce capabilities in the current conversation; and

explains that delivery details will still be required before order confirmation.

12.5 Existing profile capabilities

Updates, corrections, address management, and saved-detail checkout reuse continue touse specification 012's dedicated capabilities and typed pending confirmation state.Do not route existing-profile changes through initial onboarding.

13. Planner Routing Rules

Add deterministic guidance:

If trusted profile projection says onboarding is incomplete and onboarding has notbeen skipped in this conversation, execute start_customer_onboarding for a greetingor first-contact message.

If onboarding is collecting and the customer supplies any requested delivery detail,execute collect_customer_onboarding_details with every confidently identified valueexplicitly present in the latest message.

If field boundaries are ambiguous, omit uncertain values and clarify; never guess aname/address split merely to populate the schema.

If onboarding is reviewing and the customer explicitly confirms the displayedproposal, execute confirm_customer_onboarding with no arguments.

If onboarding is reviewing and the customer supplies corrections, executecollect_customer_onboarding_details with only the corrected values and review again.

Do not invent a missing field from conversation style, profile name, phone sender ID,assistant text, or catalog data.

If onboarding is collecting and the customer declines or asks to skip, executeskip_customer_onboarding.

If the customer makes a clear catalog/product request instead of supplying details,allow the applicable commerce capability and mark onboarding skipped for the currentconversation through deterministic session policy; do not repeatedly intercept everycommerce turn.

If onboarding is complete, never start it again.

Do not use onboarding capabilities to overwrite an existing completed profile.

One capability decision remains the rule for each graph execution.

Prompt capability descriptions must explain behavior, while services remain the sourceof invariants and persistence rules.

14. Repository Contract

Extend the existing saved-delivery repository with an atomic onboarding operation,adapted to project naming:

async def complete_onboarding(
    *,
    tenant_id: UUID,
    channel: ChannelName,
    channel_customer_id: str,
    customer_name: str,
    phone_number: str,
    delivery_address: str,
    consent_version: str,
    consented_at: datetime,
    request_id: str,
) -> SavedDeliveryProfile: ...

It must run in one PostgreSQL transaction:

lock or create the tenant/channel/customer-scoped profile;

detect an already completed profile;

return the existing completed result for the same idempotent request;

reject conflicting overwrite through onboarding;

write normalized name and unverified phone;

create or reuse the initial default address safely;

record consent and onboarding completion;

record the trusted request ID; and

commit.

Every query must be scoped by trusted tenant_id, channel, andchannel_customer_id. A phone number is never the lookup key for profile ownership.

15. Idempotency and Concurrency

Use trusted request_id at the side-effecting persistence boundary.

Retrying the same request must return the original successful profile withoutcreating duplicate addresses.

Concurrent first messages for the same trusted channel customer must serialize onthe same profile identity.

Enforce the existing profile uniqueness constraint in PostgreSQL.

Lock the profile row or equivalent identity scope during completion.

A concurrent completed-profile result must not be overwritten by stale pending state.

Database deadlock/serialization handling follows the project's established boundedretry policy.

Never depend on LLM determinism for idempotency.

16. Response Outcomes

Approved outcomes must carry English source meaning and stable IDs; the Response Nodelocalizes them according to existing response rules.

Suggested IDs:

Situation

Fragment ID

Follow-up ID

First-time disclosure

customer-onboarding-started

request-customer-profile

Missing details

customer-onboarding-incomplete

request-missing-profile-details

Invalid phone

invalid-onboarding-phone

correct-onboarding-details

Details ready for review

customer-onboarding-review

confirm-customer-profile

Ambiguous extraction

ambiguous-onboarding-details

clarify-onboarding-details

Saved successfully

customer-profile-saved

continue-shopping-after-onboarding

Already completed

customer-profile-already-saved

continue-shopping-returning-customer

Skipped

customer-onboarding-skipped

continue-as-guest

Guest cannot persist

profile-memory-unavailable-for-guest

continue-as-guest

Temporary failure

customer-profile-temporarily-unavailable

retry-customer-onboarding

Rules:

When multiple details are missing, ask for all of them in one clear question.

During review, render name, phone, and address as separate labelled values and askexactly one confirmation question.

Preserve the preferred customer name exactly where it is approved for display.

Never expose full phone or address merely to prove that saving succeeded.

Never use verified, authenticated, or confirmed owner wording.

Deterministic fallbacks must preserve the same approved meaning and follow-up.

17. Checkout Integration

A completed profile becomes available to the existing saved-delivery-details flow.

Initial onboarding does not directly confirm an order or create a cart.

Saved details must not silently overwrite checkout values already provided in thecurrent conversation.

Use the existing saved-profile acceptance and overwrite-confirmation behavior.

Confirmed orders retain immutable delivery snapshots.

Updating or deleting a profile later never changes historical orders.

A skipped or guest customer supplies one-time checkout details before confirmation.

18. Privacy and Security

Encrypt database connections and backups.

Restrict profile-table access to the application database role that needs it.

Mask phone numbers and addresses in logs and operational events.

Do not use customer names, phone numbers, addresses, channel identifiers, or messagebodies as metric labels.

Do not print capability arguments containing PII.

Do not include full saved details in ordinary planner prompts.

Apply data-retention, export, correction, and deletion policies in the later privacymilestone.

Deleting a saved profile must not corrupt immutable legal/order records.

The frontend must not separately cache parsed phone/address fields; its existingvisible transcript behavior remains governed by the frontend privacy specification.

Rate-limit onboarding attempts at the API/channel boundary according to the latersecurity-hardening milestone.

19. Observability

Use low-cardinality events/metrics such as:

onboarding offered;

onboarding review presented;

onboarding review corrected;

onboarding completed;

onboarding skipped;

onboarding validation failed by safe field category;

profile hydration succeeded/failed;

idempotent completion reused; and

persistence conflict or temporary failure.

Never include raw PII, conversation text, channel customer identifiers, profile IDs, orrequest IDs in metric labels. Correlation IDs may appear in protected structured logsunder existing logging policy.

20. Testing Strategy

20.1 Unit tests

First visit identifies all three missing fields.

Partial details retain valid values and request all remaining fields together.

Unlabelled values in different orders are extracted when boundaries are clear.

Ambiguous name/address boundaries are omitted and clarified rather than guessed.

Empty name/address and invalid phone are rejected.

Complete proposed details enter review without durable persistence.

Explicit review confirmation is required before persistence.

Review corrections retain unchanged fields and produce a new review.

Valid phone remains unverified.

Skip clears pending state.

Completed profile is not offered onboarding again.

Existing completed values cannot be overwritten through onboarding.

Response outcomes contain correct fragment and follow-up IDs.

20.2 Repository integration tests

Profile and initial address are created in one transaction.

Failure before commit creates neither a completed profile nor orphan address.

Same request ID returns the original result.

Concurrent completion creates one profile and one initial address.

Tenant and channel isolation are enforced.

Phone number cannot resolve another customer's profile.

Existing profile/address data survive migration.

20.3 Planner tests

New stable customer greeting routes to start_customer_onboarding.

Natural all-field response routes to collect_customer_onboarding_details with exact,confidently extracted values.

Partial multilingual response passes only supplied values.

Ambiguous B-68 Samad Colony 9560717170 does not guess whether Samad is a name.

Explicit review confirmation routes to confirm_customer_onboarding with noarguments.

Review correction routes to collect_customer_onboarding_details with only changedvalues.

skip routes to skip_customer_onboarding.

A clear product request can continue commerce without repeated onboarding interception.

Returning customer routes normally and is not recollected.

Planner never supplies trusted context, consent timestamps, IDs, or verification flags.

20.4 Response tests

Verify first-time, partial, ambiguous, review, correction, saved, skipped, guest, andreturning outcomes in:

English;

Hindi script;

Hinglish/Latin script; and

at least one additional supported language.

Product names and other approved business values remain unchanged under existingresponse rules.

20.5 End-to-end tests

Start a web conversation with a stable development identity.

Send Hi.

Receive one localized question requesting name, phone, and address together.

Supply all three details in one message.

Verify no durable profile has been completed yet and receive a field-by-field review.

Confirm the review explicitly.

Verify one profile, one default address, unverified phone, consent, and completion.

Start a new conversation with the same stable identity.

Verify a returning greeting without recollecting details.

Proceed through checkout and verify saved-detail reuse follows specification 012.

Repeat the flow for:

partial details;

unlabelled clear details in different field orders;

ambiguous name/address boundaries;

review correction and reconfirmation;

review rejection without corrections;

invalid phone correction;

skip and guest checkout;

duplicate HTTP/channel request;

concurrent first messages;

database failure; and

cross-tenant/channel isolation.

21. Acceptance Criteria

This milestone is complete when:

A first-time stable customer receives a localized welcome and one question askingfor all missing profile fields together.

Name, phone, and address can be supplied in one natural-language message.

Clear unlabelled input such as b-68 2nd Floor dda colony samad 9560717170 can beproposed as address, name, and phone without requiring field order.

Genuinely ambiguous name/address boundaries are clarified instead of guessed.

Partial replies do not force three separate capability turns for fields alreadyprovided.

Complete extracted details are displayed as a field-by-field review before anydurable completion.

Profile and initial default address are saved atomically only after explicit reviewconfirmation.

Every stored phone is marked unverified.

Returning customers are recognized by trusted tenant/channel identity and are notasked for the same details again.

Guest and skipped customers can browse and order using one-time checkout details.

Existing completed profiles cannot be silently overwritten.

Duplicate and concurrent requests cannot create duplicate profiles or addresses.

Full phone numbers and addresses are absent from routine prompts, logs, and metriclabels.

Existing cart, checkout, order, inventory, REST, web, and WhatsApp behavior remainsbackward compatible.

No new LangGraph node or duplicate customer-profile table is introduced.

Unit, integration, planner, response, concurrency, migration, and end-to-end testspass.

22. Deferred Work

OTP verification and authenticated phone ownership.

Authenticated cross-device web accounts.

Profile sharing or linking across channels.

Marketing preferences and promotional messaging.

Address validation, geocoding, and delivery eligibility.

Customer self-service profile screen.

Formal privacy export/deletion portal.

Staff customer-management interface.
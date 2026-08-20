Sequential Customer Onboarding Flow Specification

1. Purpose

Replace the current mixed onboarding prompts with one clear, sequential customer
journey:

Greeting
-> name and phone
-> WhatsApp delivery location
-> building/address details
-> profile review
-> explicit confirmation
-> durable profile save
-> category selection

The system must retain valid information between turns and ask only for the next
missing requirement. It must never return to the legacy complete-text-address prompt
after a WhatsApp location has become the selected onboarding method.

This milestone refines specifications 012, 016, 027, 029, and 030. It supersedes only
their conflicting onboarding conversation rules. Existing identity, tenant isolation,
consent, serviceability, localization, persistence, security, and checkout rules remain
authoritative.

Specification 030's FIFO and channel-ordering work remains deferred. This milestone
does not require strict FIFO, message bursting, message coalescing, RabbitMQ, Kafka,
SQS, or another queue.

2. Problem Statement

The current first response contains two overlapping instructions:

To save reusable delivery details, share your name and phone number plus the WhatsApp
location attachment for the delivery destination.

Please share any missing name or phone number and send the delivery destination using
WhatsApp Location.

After the customer supplies a name and phone number, the application may then emit the
legacy fallback:

The valid details supplied so far have been retained for this review. What complete
delivery address would you like me to save? You may reply as Name, Phone, and Complete
address.

This happens because the older text-address onboarding flow and the newer
location-first flow remain simultaneously eligible. Fragment text and follow-up text
also repeat the same instruction.

The corrected design uses one canonical onboarding stage and one missing-requirement
resolver. Every successful turn advances or preserves that state deterministically.

3. Goals

Greet a first-time customer before requesting personal details.

Keep each customer-facing request short and focused.

Collect name and phone number before requesting a delivery location.

Accept name and phone together or separately without discarding either value.

Request a WhatsApp location only after name and phone are available.

Check the supplied location against active tenant delivery zones.

Request flat/house number, floor, entrance, and landmark only after a serviceable
location is available.

Retain valid pending fields across turns.

Ask only for fields that are still missing or invalid.

Review the complete proposed profile before persistence.

Persist the reusable profile only after explicit customer confirmation.

Continue to category selection after successful confirmation.

Localize every response to the latest customer's language, script, tone, and chat
style while preserving approved business facts.

Preserve the existing Planner -> Execute -> Response graph.

4. Non-goals

Strict per-conversation FIFO or channel burst processing.

A broker such as RabbitMQ, Kafka, or SQS.

Collecting all onboarding information in a single mandatory customer message.

OTP verification or verified phone ownership.

Continuous or live location tracking.

Deriving building details from latitude and longitude.

Using a locality, PIN code, geocoder, or LLM as the serviceability authority.

Persisting a profile without explicit confirmation.

Adding an onboarding LangGraph node.

Calling one capability from another capability.

Changing checkout, payment, inventory, fulfilment, or notification behavior.

5. Frozen Architecture

The graph remains:

Planner -> Execute -> Response -> END

The responsibility boundaries remain:

Channel adapters authenticate and normalize inbound text or location messages.

Trusted runtime context carries the current location attachment.

The planner selects exactly one capability.

Capabilities validate typed arguments and return approved outcomes.

The onboarding service owns stage transitions and field-preserving merges.

The delivery service and zone repository decide serviceability.

PostgreSQL owns durable profiles and saved addresses.

Checkpointed commerce state owns an unconfirmed onboarding proposal.

The response node localizes approved meaning but never changes onboarding state.

6. Canonical Onboarding State

Use one checkpointed aggregate as the source of unconfirmed onboarding progress:

class OnboardingStage(str, Enum):
    COLLECTING_IDENTITY = "COLLECTING_IDENTITY"
    COLLECTING_LOCATION = "COLLECTING_LOCATION"
    COLLECTING_ADDRESS_DETAILS = "COLLECTING_ADDRESS_DETAILS"
    REVIEWING_PROFILE = "REVIEWING_PROFILE"
    COMPLETED = "COMPLETED"


class PendingDeliveryLocation(BaseModel):
    inbound_message_id: UUID
    latitude: Decimal
    longitude: Decimal
    delivery_zone_id: UUID
    locality_display: str | None = None


class PendingCustomerOnboarding(BaseModel):
    stage: OnboardingStage = OnboardingStage.COLLECTING_IDENTITY
    customer_name: str | None = None
    phone_number: str | None = None
    delivery_location: PendingDeliveryLocation | None = None
    address_details: str | None = None

The exact model names may follow current repository conventions, but there must be only
one logical aggregate and one stage source of truth.

Rules:

COMPLETED means the confirmed profile was durably saved.

A phone number collected here remains unverified.

Raw coordinates must not be placed in planner-visible conversation text.

Pending state must not be treated as durable consent.

A partial update must never replace an existing valid field with None or an empty
value.

A rejected location must not replace the last valid pending location.

7. Deterministic Stage Resolver

After every valid merge, calculate the stage in this order:

def resolve_onboarding_stage(pending: PendingCustomerOnboarding) -> OnboardingStage:
    if not pending.customer_name or not pending.phone_number:
        return OnboardingStage.COLLECTING_IDENTITY
    if pending.delivery_location is None:
        return OnboardingStage.COLLECTING_LOCATION
    if not pending.address_details:
        return OnboardingStage.COLLECTING_ADDRESS_DETAILS
    return OnboardingStage.REVIEWING_PROFILE

Only successful durable confirmation changes REVIEWING_PROFILE to COMPLETED.

The resolver must be shared by the relevant onboarding capabilities or domain service.
Prompts must not independently infer the next stage.

8. Customer Experience

8.1 First interaction

When a stable channel customer has no completed saved profile, greet them and ask only
for name and phone number.

Approved meaning:

Hi! Welcome to MeatUncle. Please share your name and phone number to get started.

Natural Hinglish example:

Hi! MeatUncle mein welcome hai 👋 Order shuru karne ke liye apna naam aur phone number
share kar dijiye.

Requirements:

Include a greeting or welcome.

Ask exactly one clear question/request covering name and phone.

Do not request location or address details in the same first response.

Do not duplicate the instruction in both the fragment and follow-up.

Do not claim the phone number will be verified.

8.2 Name and phone supplied together

USER: Samad 9560717170
ASSISTANT: Thanks Samad! Ab delivery ke liye apni WhatsApp location share kar dijiye 📍

The application must retain both valid fields and advance to
COLLECTING_LOCATION.

8.3 Name or phone supplied separately

USER: Samad
ASSISTANT: Thanks Samad! Ab apna phone number share kar dijiye.

USER: 9560717170
ASSISTANT: Thanks! Ab apna naam share kar dijiye.

After the remaining identity field arrives, request the WhatsApp location. Never ask
for the already retained field again.

8.4 WhatsApp location supplied

The location capability obtains coordinates only from trusted inbound context and
checks active tenant delivery zones.

When serviceable:

Location mil gayi 👍 Ab flat/house number, floor, entrance aur nearby landmark share
kar dijiye.

The application advances to COLLECTING_ADDRESS_DETAILS.

When outside the delivery area:

Sorry, abhi hum is location par delivery nahi karte. Kya aap doosri delivery location
share karna chahenge?

The stage remains COLLECTING_LOCATION.

When the customer sends a normal Google Maps URL as text rather than a normalized
WhatsApp location attachment, follow the existing location-link policy. Do not let the
LLM invent coordinates. If links are not an explicitly supported trusted input, ask
for the WhatsApp Location attachment.

8.5 Building/address details supplied

The requested text may contain flat or house number, floor, entrance directions, and a
nearby landmark. It is complementary to the pin and does not replace it.

USER: B-68, 2nd Floor, DDA Colony, near XYZ School
ASSISTANT: Please confirm your delivery details:

- Name: Samad
- Phone: ****7170
- Address: B-68, 2nd Floor, DDA Colony, near XYZ School

Kya yeh details sahi hain?

Do not show raw latitude or longitude by default. A safe area/locality label may be
shown when provided by trusted reverse-geocoding enrichment.

8.6 Confirmation

Only an explicit affirmative response while REVIEWING_PROFILE may execute the
confirmation capability.

On success:

Aapki delivery details save ho gayi hain. Aap kaunsi category browse karna chahenge?

The approved outcome may include active category options fetched from the database.
Do not say “Welcome back” immediately after a first-time profile confirmation.

On rejection or correction intent, retain the proposal and ask which detail should be
changed. Existing typed correction capabilities may be reused.

9. Capability Routing

Capability names may follow current code, but the routing behavior must be equivalent
to the following:

Current stage

Latest customer input

Action

No profile/pending state

Any first message

Start onboarding and greet

COLLECTING_IDENTITY

Name and/or phone

Collect identity fields

COLLECTING_LOCATION

Trusted location attachment

Submit delivery location

COLLECTING_LOCATION

Unrelated text

Request WhatsApp location

COLLECTING_ADDRESS_DETAILS

Address-detail text

Collect address details

REVIEWING_PROFILE

Explicit confirmation

Confirm and persist profile

REVIEWING_PROFILE

Rejection/correction

Enter the existing correction flow

COMPLETED

Commerce intent

Continue normal commerce routing

Planner rules:

Onboarding requirements take precedence for a first-time stable customer until the
profile is confirmed, subject to any existing guest-browsing policy.

Never route name/phone text to the address-detail field merely because it is free
text.

Never route address-detail text before a serviceable location exists.

Never manufacture location arguments from message text.

Never select the legacy complete-address follow-up during location-first onboarding.

Continue to enforce one planner decision per graph invocation.

10. Identity Extraction and Validation

The identity capability accepts sparse values:

class CustomerIdentityArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_name: NonEmptyText | None = None
    phone_number: NonEmptyText | None = None

Rules:

At least one field must be supplied.

Normalize and validate each supplied field through domain policies.

Preserve valid values already present in pending state.

Reject empty, ambiguous, or malformed values without erasing other fields.

The planner may extract Samad 9560717170 as name and phone because both values are
sufficiently distinguishable.

Do not pass trusted channel identity, tenant ID, conversation ID, coordinates, zone
ID, consent, or completion status as LLM arguments.

11. Address-Detail Validation

The address-detail capability accepts only customer-supplied building instructions:

class AddressDetailsArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    address_details: NonEmptyText

Requirements:

Trim surrounding whitespace and enforce configured length bounds.

Reject text containing only punctuation or an unsupported attachment.

Do not require every customer to use all labels such as flat, floor, entrance, and
landmark; require a useful non-empty building-level description according to the
existing address policy.

Do not geocode this text to determine serviceability.

Do not replace the already accepted location pin.

12. Approved Outcome Design

Approved fragments should state only newly completed facts. The follow-up should carry
the single next request.

Identity complete

{
  "fragments": [
    {
      "id": "customer-identity-received",
      "text": "Customer name and phone number were received."
    }
  ],
  "follow_up": {
    "id": "request-delivery-location",
    "question": "Please share the delivery destination using WhatsApp Location."
  }
}

Location complete

{
  "fragments": [
    {
      "id": "delivery-location-serviceable",
      "text": "Delivery is available at the shared location."
    }
  ],
  "follow_up": {
    "id": "request-address-details",
    "question": "Please share the flat or house number, floor, entrance, and a nearby landmark."
  }
}

Do not include a second fragment that repeats the follow-up request. The response node
may combine the factual fragment and one question naturally.

13. Legacy Prompt and Resolver Removal

During location-first onboarding, remove or make ineligible wording equivalent to:

What complete delivery address would you like me to save? You may reply as Name,
Phone, and Complete address.

Also remove or make ineligible first-turn wording that asks for identity and location
at the same time.

Implementation rules:

There must not be two independent next_missing_detail functions for onboarding.

Text-address fallback, when retained for unsupported channels, must be represented by
an explicit onboarding mode or channel policy rather than inferred from a missing
field.

WhatsApp location-first onboarding must never fall through to the text-address
fallback.

The response prompt cannot repair a contradictory execution outcome; the execute
result itself must contain one coherent next step.

14. Channel Policy

Use an explicit policy such as:

class DeliveryInputMode(str, Enum):
    WHATSAPP_LOCATION = "WHATSAPP_LOCATION"
    TEXT_ADDRESS = "TEXT_ADDRESS"

For Meta WhatsApp with location support, select WHATSAPP_LOCATION. Other channels
may continue using TEXT_ADDRESS only when their approved channel policy requires it.
Do not switch modes mid-onboarding merely because the customer sent ordinary text.

If the customer cannot share a location, an explicit fallback action may switch modes
according to specification 029. That switch must be deliberate, persisted in pending
state, and acknowledged to the customer.

15. Persistence and Consent

Name, phone, location, and address details remain checkpointed proposal data until
explicit confirmation.

Confirmation must write the profile/address atomically using the existing service and
repository transaction.

Persist trusted coordinates and the selected delivery zone according to
specification 029.

Record consent timestamps and provenance according to specifications 012 and 016.

Keep phone_verified = false until a future verification milestone.

Replayed confirmation must remain idempotent under the existing profile-save policy.

A failed durable save must not mark onboarding COMPLETED.

16. Returning Customers

When a completed profile exists:

Do not run first-time onboarding.

Greet naturally when the latest message is a greeting.

Offer category selection as the next approved commerce step according to
specification 027.

Do not re-request name, phone, location, or address unless the customer asks to
update details or the saved address fails a required serviceability recheck.

“Welcome back” is appropriate only for a genuinely returning customer, never in the
immediate response that confirms their first profile save.

17. Localization and Response Quality

The response node must:

Match the latest customer's language, script, tone, and natural chat style.

Keep product names, category names, phone masks, and approved business data exact.

Translate or naturally rephrase surrounding onboarding instructions.

Ask exactly one clear follow-up question when a follow-up exists.

Avoid formal internal phrases such as “valid details supplied so far have been
retained for this review.”

Avoid repeating the same request in adjacent sentences.

Avoid claiming identity, phone, or address verification.

For the example customer style, acceptable wording includes:

Hi! MeatUncle mein welcome hai 👋 Apna naam aur phone number share kar dijiye.

It should not be hardcoded as the only output. Other languages and styles must be
supported through the grounded response node.

18. Error Handling

Invalid phone: retain a valid name and request only a valid phone number.

Invalid/empty name: retain a valid phone and request only the name.

Missing location attachment: remain in COLLECTING_LOCATION and explain briefly how
to use WhatsApp Location.

Unsupported location: remain in COLLECTING_LOCATION and request another location.

Serviceability dependency unavailable: return a safe temporary failure; do not
accept or reject the location speculatively.

Invalid address details: remain in COLLECTING_ADDRESS_DETAILS and request useful
building details.

Profile save failure: remain in REVIEWING_PROFILE and return a retry-safe temporary
failure.

19. Observability and Privacy

Add or reuse low-cardinality events/metrics for:

onboarding stage entered;

identity accepted or rejected;

location accepted, outside zone, or temporarily unavailable;

address details accepted or rejected;

profile review shown;

profile confirmation succeeded or failed;

legacy follow-up selected unexpectedly.

Never put names, phone numbers, address text, coordinates, message bodies, or channel
customer IDs in metric labels. Logs must use safe internal identifiers and existing PII
redaction rules.

20. Testing Requirements

20.1 Domain tests

Empty pending state resolves to COLLECTING_IDENTITY.

Name alone remains COLLECTING_IDENTITY and asks only for phone.

Phone alone remains COLLECTING_IDENTITY and asks only for name.

Name plus phone resolves to COLLECTING_LOCATION.

Serviceable location resolves to COLLECTING_ADDRESS_DETAILS.

Address details resolve to REVIEWING_PROFILE.

Only successful confirmation resolves to COMPLETED.

Sparse merges preserve previously valid values.

Invalid values do not erase valid values.

20.2 Capability tests

Samad 9560717170 produces identity-complete outcome plus location follow-up.

Identity-complete outcome never asks for a complete text address.

Location is read only from trusted inbound context.

Serviceable location asks for building details.

Outside-zone location asks for another location.

Building details produce a masked profile review.

Explicit confirmation persists exactly once.

First-time confirmation does not produce “Welcome back.”

20.3 Planner tests

First-time Hi starts onboarding rather than direct category browsing.

At COLLECTING_IDENTITY, identity text routes to identity collection.

At COLLECTING_LOCATION, a location attachment routes to location submission.

At COLLECTING_LOCATION, unrelated text cannot become an address.

At COLLECTING_ADDRESS_DETAILS, address text routes to address-detail collection.

At REVIEWING_PROFILE, an affirmative response routes to confirmation.

No planner path calls a legacy all-fields onboarding capability for WhatsApp mode.

20.4 Response tests

First response contains a greeting and only the name/phone request.

Every response contains at most one question.

Fragment and follow-up meaning are not duplicated.

Hinglish customer messages receive natural Hinglish responses.

Product and business facts remain unchanged.

Internal state terminology is not exposed.

20.5 End-to-end regression

Required scenario:

USER: Hi
ASSISTANT: greets and asks for name and phone only

USER: Samad 9560717170
ASSISTANT: asks for WhatsApp delivery location only

USER: <serviceable WhatsApp location>
ASSISTANT: confirms serviceability and asks for building details only

USER: B-68, 2nd Floor, DDA Colony, near XYZ School
ASSISTANT: shows masked profile review and asks for confirmation

USER: Haa
ASSISTANT: confirms save and offers active category choices

Assert throughout that the application never emits the legacy “complete delivery
address ... Name, Phone, and Complete address” prompt.

21. Acceptance Criteria

This milestone is complete when:

A new customer is greeted before any data request.

The first request asks only for name and phone.

Name and phone may arrive together or separately and are retained correctly.

Once identity is complete, the only next request is WhatsApp location.

A serviceable pin leads only to the building-details request.

Complete proposed details lead to one masked review and confirmation question.

Durable persistence happens only after explicit confirmation.

Successful first-time confirmation proceeds to category selection without saying
“Welcome back.”

No location-first WhatsApp path selects the legacy complete-address prompt.

Responses remain concise, grounded, non-duplicative, and multilingual.

Existing three-node graph, serviceability authority, tenant isolation, and privacy
boundaries remain intact.

All new and existing scoped tests pass.

22. Recommended Implementation Order

Introduce or consolidate the canonical pending onboarding aggregate and stages.

Implement the deterministic stage resolver and sparse merge behavior.

Separate identity collection from address-detail collection.

Make WhatsApp delivery input mode explicit.

Update planner capability descriptions and routing rules.

Update greeting and approved outcome fragments/follow-ups.

Remove the legacy complete-address resolver path from WhatsApp mode.

Connect location success to building-detail collection.

Connect profile confirmation success to database-backed category selection.

Add unit, capability, planner, response, and end-to-end regression tests.

Update architecture/current-status documentation after verification.
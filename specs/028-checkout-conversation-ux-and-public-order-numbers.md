Checkout Conversation UX and Public Order Numbers Specification

1. Purpose

Make the completed customer checkout flow concise, readable, correctly staged, and safefor WhatsApp and other messaging channels.

This milestone fixes four observed customer-experience problems:

category, product, cart, delivery, payment, and confirmation content is difficult toscan in chat;

a customer who has just completed onboarding is incorrectly greeted withWelcome back;

checkout does not clearly disclose or select the payment method; and

customer-facing order confirmation exposes an internal UUID instead of a readable,stable order number.

This specification extends the existing checkout, saved-delivery-details, online-payment,notifications, category-led shopping, and response-composition specifications. Existingdomain, idempotency, inventory, order, notification, and provider rules remainauthoritative unless this specification explicitly strengthens the customer-facingcontract.

2. Prerequisites

Persisted carts and cart totals.

Checkout and durable order creation from specification 005.

Checkout correction and abandonment from specification 009.

Saved delivery profiles from specifications 012 and 016.

Payment lifecycle contracts from specification 013.

Customer order notifications from specification 019.

Category-led shopping from specification 027.

Meta WhatsApp delivery from specification 026.

Strict structured Response Node validation and deterministic fallback rendering.

3. Goals

Produce readable WhatsApp-safe customer messages with clear sections and one action atthe end.

Keep channel presentation deterministic enough that critical values and ordering neverdepend on LLM creativity.

Distinguish a newly saved profile from a genuinely returning customer.

Disclose the payment method before final order confirmation.

Ask the customer to choose a payment method only when two or more currently enabledmethods are available.

Use Cash on Delivery deterministically when it is the only enabled operational method,while still showing it in the final review and obtaining explicit order confirmation.

Preserve the provider-neutral payment selection boundary for future online payments.

Generate and persist a unique, immutable, human-readable public order number.

Keep internal UUIDs internal while retaining them as primary/foreign keys.

Show a complete final review with cart items, totals, masked contact details, deliveryaddress, payment method, and exactly one explicit confirmation question.

Keep every message localized to the customer's latest language, script, tone, andnatural mixed-language chat style.

Preserve the frozen Planner -> Execute -> Response graph.

4. Non-goals

Enabling a production online payment provider.

Asking customers to choose an unavailable or unconfigured payment method.

Treating COD as paid at order confirmation.

Replacing UUID primary keys, foreign keys, idempotency keys, or provider identifiers.

Allowing customers to choose a payment provider directly.

Using the LLM to calculate prices, totals, taxes, discounts, shipping, or order numbers.

HTML, Markdown tables, images, WhatsApp interactive lists/buttons, or rich cards.

A new LangGraph node.

Rewriting fulfilment, reservation, cancellation, notification, or reconciliationworkflows.

Displaying full personal data in normal status notifications or operational logs.

5. Frozen Architecture

The graph remains:

Planner -> Execute -> Response -> END

Responsibilities remain separated:

Planner
    -> chooses one typed capability
Capability
    -> validates arguments
Commerce service
    -> owns checkout/payment/order invariants and Decimal calculations
Repository transaction
    -> persists authoritative state and public order number
Approved execution outcome
    -> contains ordered semantic fragments, values, options, and one follow-up
Response Node
    -> localizes and composes readable channel text
Deterministic fallback
    -> renders the same approved meaning safely

Rules:

Business decisions must not move into response prompts.

Presentation formatting must not alter authoritative business values.

Capabilities must not call other capabilities.

Shared service logic may be reused by checkout, payment, order-status, notification,and staff APIs.

PostgreSQL remains authoritative for orders, payment selection, and public ordernumbers.

Checkout stage remains checkpointed short-term state until a durable order is created.

6. Correct Customer Journey Semantics

6.1 Newly onboarded customer

Immediately after profile confirmation, use approved meaning such as:

Your delivery details have been saved for future orders.

Do not use:

Welcome back

The customer is still in the same onboarding journey and has not returned.

6.2 Returning customer

Welcome back is allowed only when all are true:

a completed durable profile existed before the current conversation entry;

the customer was resolved through trusted channel identity; and

this is the first customer-entry response of a new/reopened conversation, not aresponse immediately following profile confirmation.

The application/session hydration boundary owns this fact. The Response Node must neverinfer returning status from the existence of profile fragments or conversation prose.

Expose a safe entry projection:

class CustomerEntryKind(str, Enum):
    FIRST_TIME = "FIRST_TIME"
    JUST_ONBOARDED = "JUST_ONBOARDED"
    RETURNING = "RETURNING"
    CONTINUING = "CONTINUING"

The planner does not set this value. Trusted runtime/profile state sets it.

6.3 Phone verification wording

Saved delivery phone data remains unverified while OTP is deferred, but this does notneed to be repeated after every successful profile or checkout action.

Mention unverified status only when it materially affects an operation, securitydecision, or an explicitly requested profile view. Never imply that saving a phonenumber verifies ownership.

7. Checkout Stage Model

Extend or align the existing checkout state with explicit payment selection:

class CheckoutStage(str, Enum):
    NONE = "NONE"
    REVIEWING_CART = "REVIEWING_CART"
    SELECTING_DELIVERY_DETAILS = "SELECTING_DELIVERY_DETAILS"
    SELECTING_PAYMENT_METHOD = "SELECTING_PAYMENT_METHOD"
    READY_TO_CONFIRM = "READY_TO_CONFIRM"

If existing code uses COLLECTING_DETAILS, retain it as the canonical name or migrateit safely; do not maintain duplicate stages with identical meaning.

Checkout state includes:

class CheckoutState(BaseModel):
    stage: CheckoutStage
    source_cart_id: UUID | None
    customer_name: str | None
    phone_number: str | None
    delivery_address: str | None
    payment_method: PaymentMethod | None

Invariants:

source_cart_id is present after checkout starts.

Delivery details are complete before payment selection/final review.

payment_method is set only to a currently eligible method.

READY_TO_CONFIRM requires source cart, all delivery details, and payment method.

Any cart, delivery, or payment correction invalidates the previous final review andrequires a new explicit confirmation.

Checkout state is not a durable order.

8. Payment Method Availability Policy

8.1 Authoritative availability

Payment methods come from typed tenant configuration or authoritative payment-policydata, never prompt text:

class PaymentMethod(str, Enum):
    CASH_ON_DELIVERY = "CASH_ON_DELIVERY"
    ONLINE = "ONLINE"

An enabled method must also be operational. For example, ONLINE is eligible only whenthe feature flag, provider configuration, currency/amount policy, and readiness checksall permit it.

Recommended service contract:

class EligiblePaymentMethod(BaseModel):
    method: PaymentMethod
    customer_label: str


class PaymentMethodPolicy(Protocol):
    async def eligible_methods(
        self,
        tenant_id: UUID,
        cart: Cart,
    ) -> tuple[EligiblePaymentMethod, ...]: ...

Customer labels are approved business values. The Response Node may localize surroundingtext, but stable payment meaning must not change.

8.2 Exactly one eligible method

When only COD is eligible:

select CASH_ON_DELIVERY deterministically in checkout state;

do not ask a fake multiple-choice question;

disclose Cash on Delivery in the final review; and

ask one explicit question to place the order with that payment method.

Example:

*Payment*
Cash on Delivery

Kya main Cash on Delivery ke saath yeh order place kar doon?

This explicit disclosure fixes the current missing payment-choice experience withoutpretending that another method exists.

8.3 Multiple eligible methods

When two or more methods are eligible, set stage to SELECTING_PAYMENT_METHOD and shownumbered options:

*Payment Method*

1. Cash on Delivery
2. Online Payment

Aap kaunsa payment method use karna chahenge?

The customer may select by current ordinal or unambiguous method name. Selection routesto select_payment_method using the existing closed enum contract.

8.4 No eligible methods

Do not enter READY_TO_CONFIRM. Return a safe temporary-unavailability outcome and keepthe active cart unchanged. Do not invent COD as a fallback when business policy disablesit.

8.5 Method becomes unavailable

Revalidate eligibility before durable confirmation. If the selected method is no longereligible:

do not create the order;

clear the stale selection;

reload eligible methods;

show the current choices or safe unavailable outcome; and

require a new final review and explicit confirmation.

9. Checkout Capability Behavior

9.1 checkout

The existing capability must:

load the authoritative active cart;

reject an empty cart;

calculate item line totals and cart total using Decimal;

return a readable cart review;

set/preserve source_cart_id; and

ask whether to proceed or continue shopping.

9.2 Saved delivery details

When an eligible saved profile exists, show a safe summary:

*Saved Delivery Details*

Name: Samad
Phone: ****7170
Address: B-68 2nd Floor DDA Colony

Kya aap yahi delivery details use karna chahenge?

Ask exactly one question. Do not ask the customer to re-enter already saved fields.

9.3 Accept saved details

After explicit acceptance:

copy the authoritative profile values into checkpointed checkout state through theexisting typed confirmation capability;

determine eligible payment methods;

auto-select the only eligible method or request selection among multiple methods; and

do not create an order yet.

9.4 select_payment_method

Reuse specification 013's capability:

class SelectPaymentMethodArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payment_method: PaymentMethod

The capability:

accepts only a closed enum;

verifies the method is currently eligible;

stores it in checkout state;

sets READY_TO_CONFIRM when all other prerequisites are present; and

returns the complete final review with one explicit confirmation question.

It never accepts provider, amount, currency, order ID, success flag, checkout URL,tenant ID, or customer identity from planner arguments.

9.5 confirm_order

Before mutation, revalidate:

stage is READY_TO_CONFIRM;

latest customer response is explicit confirmation in the current final-review context;

source cart is still active and non-empty;

cart contents/totals have not changed unexpectedly;

delivery details are complete;

selected payment method is still eligible;

stock/reservation rules pass; and

trusted request idempotency is available.

COD confirmation creates one confirmed order. Online payment follows specification 013and must not be described as confirmed before verified provider success.

10. Monetary Calculation and Display

All monetary values are calculated by deterministic domain/application code usingDecimal and immutable/current authoritative price snapshots as required by theexisting cart/order rules.

For each item:

line_total = quantity * unit_price

Cart total:

subtotal = sum(line_total)
total = subtotal + configured charges - configured discounts

If taxes, shipping, discounts, or other charges are not implemented, do not display orinvent them. In that case total == subtotal.

Create an approved money formatter outside the LLM:

class MoneyFormatter(Protocol):
    def format(self, amount: Decimal, currency: str) -> str: ...

Rules:

Use one currency representation consistently within one message/conversation surface.

For the current INR WhatsApp experience, prefer configured output such as ₹320 or₹320.00; do not mix INR 320.00 with ₹320.00 in the same flow.

Do not remove meaningful fractional values.

Preserve the canonical product sales unit.

Never perform arithmetic in the Response Node.

Confirmed orders store monetary snapshots; later product changes do not rewrite them.

11. WhatsApp-Readable Composition

11.1 General format

Customer-facing WhatsApp text must:

use short paragraphs separated by exactly one blank line;

place one numbered option/item on its own line;

use WhatsApp-compatible *bold* only for short headings, totals, order numbers, andessential labels;

avoid Markdown tables, heading syntax (#), nested bullets, and excessive decoration;

place exactly one requested customer action/question at the end;

avoid joining success meaning, options, and follow-up into one long paragraph;

omit periods after standalone numbered options;

use at most one relevant status emoji per section/message by default;

remain useful when bold/emoji formatting is not rendered; and

stay within the configured provider text limit.

11.2 List layout

Use list layout when rendering categories, products, cart items, delivery fields, orpayment options. Preserve approved fragment order and option numbers.

11.3 Paragraph layout

Use paragraph for a short success/error plus one question when no itemized values arepresent.

11.4 One action per message

A message may contain several approved sections, but it must end with one clear action:

Kya main yeh order place kar doon?

Do not end with several questions such as payment choice, delivery correction, andconfirmation together.

11.5 Deterministic fallback

Fallback rendering must understand approved section/list metadata or equivalent fragmentkinds. It must preserve blank lines, item order, totals, masking, payment meaning, andthe single follow-up question without relying on an LLM.

12. Approved Final Review

Before order creation, display one complete review grounded in current authoritativestate:

🛒 *Order Summary*

1. Chicken Breast
   10 kg × ₹320/kg = ₹3,200

*Total: ₹3,200*

*Delivery*
Name: Samad
Phone: ****7170
Address: B-68 2nd Floor DDA Colony

*Payment*
Cash on Delivery

Kya main yeh order place kar doon?

Rules:

Show item names, quantities, units, unit prices, and line totals exactly as approved.

Show one deterministic total.

Mask the phone number using the existing privacy policy.

Show only the delivery details necessary for the customer to verify this order.

Never show internal cart ID, order UUID, profile ID, tenant ID, inventory IDs, oridempotency key.

If the customer corrects cart, delivery, or payment data, regenerate the completereview and require new explicit confirmation.

13. Public Order Number

13.1 Internal and public identities

Every order has both:

class Order(BaseModel):
    id: UUID
    public_order_number: str

id remains the internal primary key and relationship identity.

public_order_number is the immutable customer/staff/support reference.

Customer-facing capabilities, notifications, mobile staff search, and safe APIprojections use public_order_number.

Internal APIs may retain UUIDs where required but must not expose them as the primarycustomer reference.

13.2 Format

Recommended default:

MU-260818-0042

Structure:

<configured tenant-safe prefix>-<YYMMDD>-<sequence padded to at least 4 digits>

Rules:

Prefix is validated business configuration, uppercase ASCII alphanumeric, bounded inlength; default example MU is not hardcoded for all tenants.

Date uses the configured business timezone and order-creation date.

Sequence is generated transactionally from PostgreSQL, never from COUNT(*),MAX()+1, the LLM, client input, or an in-memory counter.

Padding is a minimum, not truncation; sequence 10000 remains 10000.

Gaps are acceptable after transaction rollback; uniqueness and immutability are moreimportant than contiguous numbering.

Do not encode customer phone, tenant UUID, customer ID, or other PII.

A public order number is a reference, not proof of ownership or authorization.

An existing canonical order_reference from specification 019 may be renamed/mapped topublic_order_number rather than creating duplicate fields, provided it satisfies theseinvariants.

13.3 Database schema

Add or align:

ALTER TABLE orders
    ADD COLUMN public_order_number varchar(32);

CREATE UNIQUE INDEX uq_orders_tenant_public_order_number
    ON orders (tenant_id, public_order_number);

CREATE INDEX ix_orders_tenant_public_order_lookup
    ON orders (tenant_id, public_order_number);

Final constraints after backfill:

NOT NULL
non-empty trimmed value
bounded validated format
UNIQUE (tenant_id, public_order_number)

The unique index already supports lookup; a duplicate separate lookup index should beomitted unless query analysis proves it useful.

Use an Alembic-managed PostgreSQL sequence or an equivalent collision-safe databasegenerator. If one global sequence is used, tenant scoping remains in the public-numberunique constraint and all lookups still require tenant ID.

13.4 Existing-order backfill

Backfill every existing order deterministically and collision-safely before applyingNOT NULL:

add nullable column and sequence/generator;

assign a generated public number to every existing order in stable order;

create/validate unique constraint;

apply NOT NULL;

update repositories/models/projections; and

retain UUIDs unchanged.

Do not derive displayed references by exposing a UUID prefix/suffix.

13.5 Transaction and retry behavior

Public number allocation occurs inside the existing order-creation transaction. Repeatedconfirmation of the same source_cart_id returns the same order and public number.

Concurrent confirmation must create at most one order for the cart. A uniqueness conflictor SQL retry must reload the existing order rather than allocate a second customer order.

14. Customer-Facing Confirmation

COD success example:

✅ *Order Confirmed*

*Order Number:* MU-260818-0042
*Payment:* Cash on Delivery
*Total:* ₹3,200

Aapka order successfully confirm ho gaya hai.

Rules:

Use the public order number, never the UUID.

State COD as a method, not as paid/payment successful.

Preserve the authoritative total and currency.

Do not promise delivery time unless an approved value exists.

Do not ask a new question unless the approved outcome contains a follow-up.

Confirmation notifications from specification 019 use the same public number.

Online payment behavior remains governed by specification 013. A provisional/awaitingpayment order must not receive COD-style confirmed wording.

15. Approved Outcome Contracts

Recommended stable IDs:

Meaning

ID

Newly saved profile

customer-profile-saved

Returning customer entry

returning-customer-welcome

Cart summary

checkout-cart-summary

Saved delivery details

saved-delivery-details

COD automatically selected/disclosed

cash-on-delivery-selected

Available payment methods

available-payment-methods

Selected payment method

payment-method-selected

Complete final review

checkout-final-review

Order confirmed

order-confirmed

Public order number

public-order-number

Payment unavailable

payment-methods-unavailable

Selected payment stale

payment-method-no-longer-available

Recommended follow-up IDs:

proceed-from-cart-review
use-saved-delivery-details
select-payment-method
confirm-order-placement
choose-another-payment-method

Rules:

IDs describe approved meaning and remain independent of customer language.

Fragment IDs include only fragments; follow-up IDs never appear in fragment_ids.

The complete final review is generated from structured approved values rather than anunrestricted English paragraph.

Every fragment ID appears exactly once and in order.

The final confirmation question has exactly one follow-up ID.

16. Response Composition Rules

Add these rules to the response prompt without weakening existing grounding rules:

WhatsApp readability:

- Use short sections separated by one blank line.
- Put each numbered item or option on its own line.
- Use WhatsApp `*bold*` only for short approved headings, totals, and order numbers.
- End with exactly one approved customer action/question when a follow-up exists.
- Never merge list options into one paragraph.
- Never add a period after a standalone numbered option.
- Keep one consistent approved currency representation.
- Never expose internal UUIDs when a public order number is provided.

Journey semantics:

- Use returning-customer meaning only when the approved outcome explicitly provides it.
- Do not add `Welcome back` after profile confirmation.
- Do not add phone-verification warnings unless approved by the execution outcome.

Payment:

- Preserve the selected payment method exactly.
- Never call COD paid.
- Never invent or offer a payment method absent from approved options.

Prompt rules improve composition but do not replace capability/service corrections. Theapproved outcome must already distinguish newly saved vs returning, provide eligiblepayment methods, totals, masking, and public order number.

17. Planner Routing Rules

Required meaning:

After cart review, explicit proceed intent advances checkout; it does not confirm theorder.

When saved delivery details are offered, explicit acceptance uses those details.

When multiple payment methods are displayed, an unambiguous method name/ordinal routesto select_payment_method.

When one payment method is automatically selected, do not ask for a selection; proceedto the complete final review.

Execute confirm_order only after explicit confirmation in the currentREADY_TO_CONFIRM context.

A generic yes resolves only against the active follow-up state and must never skipdelivery/payment stages.

Payment choice is never inferred from unrelated assistant text or an expired list.

Order status/cancellation/reorder lookup uses public order number when the customersupplies one, under existing ownership/tenant rules.

Never place an order merely because the customer selected COD or accepted saveddelivery details.

All rules apply across languages, scripts, transliteration, informal spelling, andmixed-language messages.

18. Staff and Notification Compatibility

Customer notifications use public_order_number as order_reference.

Staff dashboard lists and searches by public order number while retaining internalUUIDs for API identity where appropriate.

Staff API lookup by public number always scopes by trusted tenant.

Logs may contain internal order UUID/public reference only under existing safe loggingpolicy; neither proves authorization.

Existing confirmed orders/backfilled references remain visible consistently acrosscustomer chat, notifications, and staff mobile application.

Provider templates use the exact persisted public order number and approved totals.

19. Persistence and Idempotency

Profile confirmation and returning-customer detection remain governed by durableprofile state.

Checkout payment selection is checkpointed until order creation.

Order creation, item snapshots, inventory effects, cart closure, initial statushistory, notification outbox insertion, and public number assignment follow existingtransactional boundaries.

source_cart_id remains the durable order-creation idempotency key.

Trusted channel request_id prevents replayed inbound messages from repeating businesseffects.

Repeated explicit confirmation returns the original order/public number.

Response retries and outbound retries reuse persisted approved outcome/order data; theydo not create a new order number.

20. Security and Privacy

Never expose internal UUIDs in ordinary customer messages when a public order numberexists.

Public order numbers must not grant access by themselves; every lookup applies trustedtenant/customer authorization rules.

Mask phone numbers in checkout review according to existing policy.

Do not include full phone/address in order status notifications unless explicitlyrequired and approved.

Never log raw checkout messages, full delivery profiles, payment credentials, tokens,provider secrets, or unrestricted response prompts.

Do not derive public order numbers from PII.

Validate configured public-number prefix and business timezone at startup.

21. Observability

Use low-cardinality metrics such as:

checkout_stage_transitions_total{from_stage,to_stage,outcome}
checkout_payment_method_selections_total{method,outcome}
checkout_final_reviews_total{method,outcome}
public_order_number_generation_total{outcome}
response_layout_fallback_total{layout,outcome}

Rules:

Do not use order numbers, order UUIDs, phone numbers, addresses, customer IDs,conversation IDs, product names, free text, or prices as metric labels.

Log controlled error categories and safe correlation IDs only.

Alert on repeated public-number uniqueness failures and order-confirmation failures.

22. Migration Requirements

Use Alembic to:

add/align orders.public_order_number or canonical order_reference;

add the PostgreSQL sequence/generator;

backfill existing orders deterministically;

add unique tenant-scoped constraint and NOT NULL;

add/align payment-method constraints if current schema assumes only COD;

preserve all internal UUIDs and foreign keys; and

provide a downgrade that does not silently destroy data required by older code.

Migration tests must run against PostgreSQL, not only generated SQL. Upgrade from thecurrent head with representative existing orders, validate uniqueness and backfill, thenexercise downgrade only to the extent it is safely supported/documented.

23. Testing Requirements

23.1 Customer-entry semantics

A just-confirmed profile receives customer-profile-saved and never Welcome back.

A returning customer entering a later conversation may receive the returning greeting.

A continuing customer mid-conversation is not greeted again.

Unverified-phone wording appears only when explicitly approved/relevant.

23.2 Readability and response validation

Categories/products/cart items render one entry per line.

Sections have stable blank-line separation.

Final follow-up is exactly one question.

WhatsApp bold syntax is balanced and limited to approved labels.

Currency display is consistent.

Structured output references every fragment/follow-up ID correctly.

Deterministic fallback preserves readable sections and approved values.

Oversized content follows specification 026's fail-closed policy.

23.3 Payment method behavior

COD-only configuration selects COD deterministically and discloses it in final review.

COD-only configuration does not show a fake numbered payment choice.

Multiple eligible methods set SELECTING_PAYMENT_METHOD and show options.

Valid name/ordinal selects only a currently displayed eligible method.

Invalid/stale method returns a localized correction/current options.

No eligible method leaves cart unchanged and prevents confirmation.

Method becoming unavailable before confirmation prevents order creation.

COD confirmation never claims payment success.

23.4 Final review and confirmation

Review contains every current cart item, line total, total, masked phone, address, andpayment method.

Totals use Decimal and match order snapshots.

Correction regenerates review and requires new explicit confirmation.

yes at saved-details stage does not skip final review.

yes at payment-selection stage cannot be interpreted as an unspecified method whenmultiple choices exist.

Explicit confirmation creates exactly one order.

23.5 Public order numbers

New orders receive non-null valid public numbers.

Concurrent order creation produces unique public numbers.

Repeated confirmation of one source cart returns the same public number.

Sequence growth beyond four digits does not truncate.

Customer messages, notifications, order status, cancellation, reorder, and staff searchuse the same public number.

Customer-facing projections do not expose UUID as the displayed order reference.

Tenant A cannot look up Tenant B's order by public number.

Public number alone does not bypass customer ownership checks.

23.6 Migration

Existing orders receive unique deterministic references.

Upgrade enforces NOT NULL and tenant-scoped uniqueness.

Existing UUID relationships remain intact.

Migration handles populated databases and sequence continuation safely.

23.7 Localization

English, Hindi, Hinglish, and a non-Latin script produce readable localized sections.

Product names, payment method meaning, quantities, units, amounts, and public ordernumbers remain exact approved values.

Error, correction, empty, and stale states match the latest customer style.

24. Acceptance Criteria

This milestone is complete when:

WhatsApp category, product, cart, delivery, payment, final-review, and confirmationmessages are readable with short sections and one action at the end.

A customer who just confirmed onboarding is told their details were saved and is notincorrectly welcomed back.

A real returning customer can receive returning-customer meaning only from trustedjourney state.

Checkout has an explicit payment-method state/policy.

COD-only configuration clearly discloses COD without presenting a fake choice.

Multiple operational methods produce a real typed selection step.

Final review displays authoritative cart lines, total, masked delivery contact,address, and selected payment method before order creation.

Every new and existing order has a unique immutable public order number.

Customer confirmations and notifications display the public number instead of UUID.

Replays, retries, and concurrent confirmations cannot create duplicate orders orpublic numbers for the same source cart.

Customer language/script/style localization preserves every approved business value.

PostgreSQL migration and automated end-to-end WhatsApp tests pass.

25. Recommended Implementation Order

Audit current checkout stages, payment model, order_reference, order projections,response fragment kinds, money formatting, and staff/notification consumers.

Add the public-order-number migration, collision-safe generator, backfill, repositorymapping, and tenant-scoped lookup.

Add/align explicit payment-selection stage and authoritative eligible-method policy.

Implement COD-only auto-selection/disclosure and multi-method selection behavior.

Correct trusted customer-entry semantics so JUST_ONBOARDED and RETURNING cannot beconfused.

Add deterministic Decimal totals, money formatting, phone masking, and structuredfinal-review projections.

Update approved outcome IDs, response rules, and deterministic fallback layout.

Update customer order capabilities, notifications, staff APIs, and staff mobile UI touse public order numbers.

Add unit, PostgreSQL repository/migration, graph routing, response, concurrency,idempotency, localization, and channel tests.

Run a live Meta WhatsApp acceptance flow from onboarding through COD confirmation andconfirm that only the readable public order number is shown.
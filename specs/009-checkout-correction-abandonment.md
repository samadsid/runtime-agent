Checkout Delivery-Detail Correction and Abandonment Specification

1. Purpose

Extend the completed cash-on-delivery customer flow so a customer can:

correct their name, phone number, or delivery address before confirming an order; and

abandon an in-progress checkout without deleting or changing the persisted cart.

This milestone changes checkout conversation state only. It must not create an order,change inventory, reserve stock, close a cart, or initiate staff fulfilment.

2. Existing Constraints

The following architecture remains frozen:

Planner -> Execute -> Response -> END

Do not add a LangGraph node.

The planner chooses one capability; it never performs business operations.

Capabilities validate input and delegate domain work where required.

PostgreSQL remains authoritative for carts, orders, and inventory.

LangGraph checkpointing stores messages and short-lived CommerceSession state.

The Response Node localizes approved outcome meaning into the language, script,tone, and chat style of the latest customer message.

Product, cart, and order ordinals remain separate namespaces.

Trusted tenant_id and conversation_id come from runtime context, never fromLLM-generated capability arguments.

3. Scope

3.1 Included

Correct one or multiple delivery details during checkout.

Ask for a replacement value when the customer names a field but omits its value.

Validate corrected values without erasing the last valid values.

Re-display the complete confirmation review after a successful correction.

Require a new explicit confirmation after any correction.

Abandon checkout and clear its short-term delivery details.

Preserve the active persisted cart when checkout is abandoned.

Multilingual and mixed-language planner routing and response composition.

Deterministic fallbacks and automated tests.

3.2 Excluded

Editing a confirmed order.

Cancelling a confirmed order; the existing customer order cancellation flow owns it.

Clearing or editing cart items; existing cart capabilities own those operations.

Stock-aware confirmation recovery.

Reordering from an existing order.

Online payments.

Staff authentication or staff fulfilment endpoints.

4. Checkout State

Extend checkpointed CheckoutState with a typed pending correction field:

class DeliveryDetailField(str, Enum):
    CUSTOMER_NAME = "customer_name"
    PHONE_NUMBER = "phone_number"
    DELIVERY_ADDRESS = "delivery_address"


class CheckoutState(BaseModel):
    stage: CheckoutStage = CheckoutStage.NONE
    source_cart_id: UUID | None = None
    customer_name: str | None = None
    phone_number: str | None = None
    delivery_address: str | None = None
    pending_delivery_correction: DeliveryDetailField | None = None

Use the repository's current field names if they differ, but preserve the behavior inthis specification.

pending_delivery_correction exists only to understand the next customer message. Itmust be stored through the LangGraph checkpointer, not in the order or cart tables.

4.1 State invariants

Corrections are allowed only in COLLECTING_DETAILS or READY_TO_CONFIRM.

source_cart_id must remain unchanged during correction.

A successful supplied replacement clears pending_delivery_correction.

Invalid replacement input must preserve every previously valid detail.

If every required detail is present after correction, the stage isREADY_TO_CONFIRM.

If any required detail remains missing, the stage is COLLECTING_DETAILS.

Abandonment resets the complete checkout state to its default NONE state.

5. Capability Contracts

5.1 update_delivery_details

Add a capability with optional arguments:

class UpdateDeliveryDetailsArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_field: DeliveryDetailField | None = None
    customer_name: NonEmptyText | None = None
    phone_number: NonEmptyText | None = None
    delivery_address: NonEmptyText | None = None

The capability may receive one or several supplied values. It must reject unknownfields. The LLM must not send tenant_id, conversation_id, source_cart_id, stage,or existing checkout values.

Behavior:

Reject the request when checkout is not collecting or reviewing delivery details.

If requested_field is supplied without a replacement value, store that field inpending_delivery_correction and ask exactly one question for its value.

If one or more replacement values are supplied, validate all of them beforeapplying any update.

Validate phone numbers with the existing PhoneValidationPolicy.

Apply supplied valid values as one immutable state update and preserve all othervalues.

Clear the pending field when its replacement has been accepted.

If required values remain missing, return the existing next-missing-detail outcome.

If all values are present, return a complete confirmation review and ask forexplicit confirmation again.

The capability must support direct corrections such as:

address B-68 New Zafrabad kar do

phone number change to 9560717170

naam Samad aur address B-68 kar do

It must also support two-turn corrections:

CUSTOMER: address change karna hai
AGENT: Naya delivery address kya hai?
CUSTOMER: B-68 New Zafrabad Delhi

On the final message, the planner uses pending_delivery_correction to map the textto delivery_address; it must not search for a product or treat the address as ageneral direct response.

5.2 abandon_checkout

Add a capability requiring no LLM arguments.

Behavior:

Accept only explicit intent to leave, stop, or cancel the current checkout.

Reset CheckoutState to its default state.

Preserve the active cart and every cart item in PostgreSQL.

Do not create, update, cancel, or delete an order.

Do not reserve, release, deduct, or restore inventory.

Return success explaining that checkout was stopped and the cart was kept.

If checkout is already NONE, return an idempotent outcome without changing anydurable data.

A secondary confirmation is not required because abandonment deletes no durable cartor order data. The customer can start checkout again from the preserved cart.

6. Approved Outcomes

Capability outcomes must contain source-language-neutral approved meaning. TheResponse Node localizes surrounding text while preserving protected business values.

Recommended stable IDs:

Situation

Fragment ID

Follow-up ID

Replacement value required

delivery-detail-correction-requested

request-corrected-delivery-detail

Invalid replacement

invalid-delivery-detail-correction

correct-delivery-detail

Invalid phone

invalid-corrected-phone-number

correct-phone-number

Correction accepted, details missing

delivery-detail-corrected

Existing next-missing-detail ID

Correction accepted, ready

delivery-details-corrected

confirm-corrected-order

Checkout abandoned

checkout-abandoned

Optional continue-shopping

No active checkout

checkout-not-active

Optional start-checkout

After a correction reaches READY_TO_CONFIRM, the approved outcome must include thecomplete current review: cart items, customer name, phone number, delivery address,payment method CASH_ON_DELIVERY, and one explicit confirmation question. It must notconfirm the order itself.

7. Planner Routing

Add mandatory routing rules:

During COLLECTING_DETAILS or READY_TO_CONFIRM, explicit requests to change,correct, replace, or update a delivery name, phone number, or address executeupdate_delivery_details.

When a correction request includes the replacement value, pass the named typedvalue in the same command.

When it names only the field, pass requested_field and let the capability requestthe value.

When pending_delivery_correction exists and the next customer message supplies avalue, execute update_delivery_details for that exact pending field.

Explicit requests to stop, exit, abandon, or cancel the in-progress checkout executeabandon_checkout.

cancel checkout must not execute confirmed-order cancel_order.

clear my cart must not execute abandon_checkout.

If cancel is genuinely ambiguous between a confirmed order and active checkout,ask one concise clarification question rather than guessing.

Never use a product search to resolve a delivery-detail correction.

Never execute order confirmation after a correction without a new explicit customerconfirmation.

These rules apply to every supported language, transliteration, informal spelling,and mixed-language chat style. Examples are illustrative, not exhaustive:

Customer message

Expected route

address change karna hai

update_delivery_details(requested_field="delivery_address")

mera number 9560717170 kar do

update_delivery_details(phone_number="9560717170")

name Samad and address B-68 kar do

One update_delivery_details call with both values

checkout rehne do

abandon_checkout

cart clear kar do

Existing clear_cart, not abandonment

8. Response Localization and Privacy

Every generated fragment and follow-up is composed into the latest customer'slanguage, script, tone, and chat style.

Mixed Hindi-English input should receive natural mixed Hindi-English output.

Product names, prices, quantities, units, option numbers, phone numbers, customernames, and addresses must remain exact when included in approved data.

The Response Node must not invent a missing unit, field value, outcome, or next step.

Follow-up questions must contain exactly the approved meaning and at most one clearquestion.

Do not log raw phone numbers or delivery addresses in planner, capability, repository,or error logs. Use IDs and field names for diagnostics.

Deterministic fallback output must include the same approved correction orabandonment meaning.

9. Persistence and Transaction Rules

No new application database table or Alembic migration is required for thismilestone.

Delivery-detail drafts and the pending correction field live in checkpointedCommerceSession only.

Abandonment updates checkpoint state only.

The active cart remains persisted and tenant-scoped in PostgreSQL.

Order data is written only by the existing explicit confirmation flow.

Final confirmation remains responsible for authoritative cart locking, stock checks,idempotency, order creation, and cart closure.

If the application writes checkpoints and returns a success response, the updatedcheckout state must be included in graph state so the configured checkpointer canpersist it. Capabilities must not write directly to LangGraph checkpoint tables.

10. Error and Recovery Behavior

Empty or whitespace-only replacement: keep the old value and ask for the same field.

Invalid phone: keep the old phone and ask for a valid phone number.

Several supplied values with one invalid value: apply none of them.

Checkout state without source_cart_id: return stale-checkout outcome and direct thecustomer to restart checkout from the persisted cart.

Source cart no longer active: do not create an order; reset stale checkout state anddirect the customer to review the current cart.

Repeated abandonment: return the same customer-safe result without side effects.

LLM composition/schema failure: use deterministic approved fallback output.

11. Implementation Placement

Suggested placement, adapted to existing repository conventions:

commerce/models/checkout.py
commerce/services/checkout_service.py
runtime/capabilities/update_delivery_details/
runtime/capabilities/abandon_checkout/
runtime/capabilities/checkout_support.py
runtime/prompts/planner/
tests/unit/
tests/integration/

Keep state transition helpers in the commerce domain or existing checkout supportmodule. Keep prompt text out of services and SQL out of capabilities.

12. Acceptance Tests

12.1 Unit tests

A named field without a value stores pending_delivery_correction and asks once.

A subsequent value updates the pending field and clears the pending marker.

A direct single-field correction preserves all other details.

A direct multi-field correction applies all valid fields atomically.

Invalid phone and empty values preserve the previous valid state.

A complete corrected checkout becomes READY_TO_CONFIRM.

A correction produces a fresh complete review and requires explicit confirmation.

Abandonment resets all checkout fields and stage.

Repeated abandonment is idempotent.

12.2 Planner tests

Correction intent routes to update_delivery_details in English, Hindi, RomanizedHindi, and representative mixed-language messages.

A pending field makes the next bare value route to the correction capability.

Checkout cancellation routes to abandon_checkout.

Confirmed-order cancellation routes to existing cancel_order.

Cart clearing routes to existing clear_cart.

Ambiguous cancellation produces one clarification, not a guessed capability.

12.3 Integration tests

Start checkout, collect details, correct address, confirm again, and create exactlyone order containing the corrected address.

Start checkout, abandon it, restart checkout, and verify the original persisted cartis still present.

Abandonment creates no order and changes no inventory or reservation records.

A correction followed by an LLM response failure returns localized-safe deterministicfallback content with exact approved IDs.

Tenant A cannot inspect or mutate Tenant B cart or checkout through supplied IDs.

13. Definition of Done

This milestone is complete when:

both capabilities are registered and represented in generated capability metadata;

planner routing covers direct, two-turn, multilingual, and ambiguous cases;

pending correction state survives a checkpointed turn;

corrections never silently confirm an order;

invalid corrections never erase valid details;

abandonment preserves the database cart and has no order or inventory side effects;

response composition and fallback remain grounded and localized;

unit and integration tests pass; and

the graph still contains only Planner, Execute, and Response nodes.

14. Deferred Next Milestones

Implement separately, in this order unless business priority changes:

stock-aware confirmation failure and recovery UX;

reorder from a previous order using current catalog price and availability;

online payment lifecycle and webhook reconciliation; and

authenticated staff fulfilment APIs.
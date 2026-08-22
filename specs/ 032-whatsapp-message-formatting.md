WhatsApp Message Formatting Specification

1. Purpose

Introduce one consistent, mobile-friendly formatting standard for every customer-facing WhatsApp message produced by the AI Commerce Agent.

This milestone improves readability and interaction clarity without changing commerce decisions, capability behavior, persistence, or workflow state.

It applies to:

replies generated during the WhatsApp customer-service window;

deterministic fallback replies;

approved WhatsApp template content where the approved template permits formatting;

all existing customer flows, including onboarding, catalog, cart, checkout, orders, errors, and notifications.

This specification does not make WhatsApp formatting the source of business truth. Products, prices, quantities, units, availability, option numbers, serviceability, payment state, and order state remain authoritative only in existing domain data and approved execution outcomes.

2. Problem Statement

Customer-facing messages are functionally correct but can be difficult to scan on a phone. Common problems include:

dense paragraphs containing several facts;

inconsistent headings, spacing, lists, totals, and follow-up questions;

selectable options that are visually indistinguishable from informational bullets;

product and category results that are hard to compare;

repeated instructions in fragments and follow-ups;

overly formal language or exposed internal terminology;

formatting differences between generated replies and deterministic fallbacks;

layouts that work in Markdown renderers but display poorly in WhatsApp.

The corrected design introduces a semantic message-formatting contract that produces predictable WhatsApp-safe text while preserving the existing grounded-response rules.

3. Goals

Make every customer message easy to scan on a mobile screen.

Present selectable choices as stable numbered lists.

Present non-selectable facts as short bullets or labeled lines.

Highlight only meaningful headings, totals, statuses, and product names.

End with at most one clear next action or question.

Preserve exact approved business facts and ordinal mappings.

Match the customer's latest language, script, tone, spelling style, and mixed-language usage.

Keep generated replies and deterministic fallbacks visually consistent.

Preserve the existing Planner -> Execute -> Response -> END graph.

Keep formatting policy centralized enough to prevent each capability from inventing a different visual style.

4. Non-goals

Changing planner routing or commerce decisions.

Adding a new LangGraph node.

Changing capability inputs, domain rules, or database state solely for presentation.

Introducing RabbitMQ, Kafka, SQS, or another broker.

Implementing typing indicators, reactions, read receipts, or presence.

Implementing reply buttons, interactive lists, catalog messages, flows, images, video, audio, or documents.

Redesigning approved Meta templates outside their approved structure.

Replacing localization with hardcoded English or Hinglish messages.

Rendering Markdown tables, HTML, cards, or web-only components in WhatsApp.

Exposing raw UUIDs, coordinates, internal state, provider errors, or operational metadata.

5. Frozen Architecture and Responsibility Boundaries

The graph remains:

Planner -> Execute -> Response -> END

Responsibilities remain:

The planner chooses exactly one next action.

Capabilities and domain services execute validated business behavior.

Capabilities return approved fragments, options, follow-ups, and authoritative facts.

The response node localizes and formats only approved meaning.

The WhatsApp adapter transports the final text and must not reinterpret commerce semantics.

Deterministic fallback rendering uses the same presentation conventions without calling another capability.

Approved Meta templates remain governed by their registered template definition and parameter contract.

Formatting must never alter state, execute a capability, reorder semantic choices, or infer missing business facts.

6. WhatsApp-Safe Formatting Contract

6.1 Allowed formatting

Customer messages may use:

short plain-text paragraphs;

a short heading using WhatsApp bold syntax: *Heading*;

numbered options using 1., 2., 3.;

informational bullets using •;

compact labeled lines such as *Total:* ₹640;

one blank line between logical sections;

limited, purposeful emoji when appropriate to the message type;

WhatsApp italic syntax only when it materially improves comprehension.

6.2 Disallowed formatting

Do not use:

Markdown tables;

HTML;

nested lists deeper than one level;

heading syntax such as # or ##;

fenced code blocks for ordinary customer messages;

decorative separators repeated across the message;

excessive capitalization, bold text, punctuation, or emoji;

raw JSON, Python representations, internal enum values, or technical error text;

links unless the approved outcome or template explicitly supplies the link;

invented Markdown features that WhatsApp does not reliably render.

6.3 Mobile length and density

Prefer one short heading followed by one content section and one next-action line.

Keep paragraphs to one or two short sentences where possible.

Put each selectable option on its own line.

Separate major sections with exactly one blank line.

Avoid blank lines inside a single product or address block unless required for clarity.

Do not repeat the same fact in a heading, fragment, summary, and follow-up.

Long result sets must follow the repository's established limit or pagination behavior; formatting must not silently truncate authoritative results.

6.4 Emphasis

Use bold sparingly for:

a message heading;

product names in a product list;

important labels such as Total, Delivery address, Payment, and Order status;

a confirmed order number or final status when already approved for display.

Do not bold every line. Do not use formatting to imply urgency, success, availability, discounts, or guarantees that the approved outcome did not provide.

6.5 Emoji policy

Emoji are optional, not required.

Use at most one heading emoji in ordinary messages unless an approved brand style explicitly requires more.

Use only context-relevant emoji.

Never use emoji as the only representation of status or meaning.

Validation, payment failure, cancellation denial, privacy, and support messages should prioritize clarity over decoration.

The response must remain complete and understandable when emoji are removed or unsupported.

7. Semantic Layout Types

The existing response composition contract may be extended only if necessary. Prefer mapping the current paragraph and list layouts into these semantic presentations rather than creating a second response system.

7.1 Short response

Use for greetings, acknowledgements, simple confirmations, and single-field requests.

<one short paragraph>

<one question, when required>

7.2 Selectable list

Use when the customer may refer to an item by ordinal.

*<Localized heading>*

1. <Option one>
2. <Option two>
3. <Option three>

<One localized selection instruction or question>

Rules:

Preserve approved option order exactly.

Preserve each option number exactly.

Never convert a selectable numbered list into bullets.

Never insert decorative numbered content that could collide with an ordinal namespace.

The final instruction may accept a number or name only when existing planner behavior supports both.

7.3 Informational list

Use when items are not selectable by ordinal.

*<Localized heading>*

• <Fact one>
• <Fact two>

Do not use numbered lines for informational facts when a later customer message could incorrectly be interpreted as an ordinal selection.

7.4 Summary

Use for carts, checkout review, saved profile review, address review, order details, and status summaries.

*<Localized heading>*

<approved detail lines or item list>

*<Important label>:* <approved value>

<One next action or question, when required>

7.5 Error or unavailable state

Use a short explanation followed by one recovery action.

<What could not be completed, in customer-friendly language.>

<One safe next step or question.>

Do not expose exception messages, provider codes, SQLSTATE values, internal retries, stack traces, capability names, state names, or identifiers.

8. Message-Type Requirements

8.1 Greeting and onboarding

Greet first-time customers naturally.

Ask only for the next missing requirement determined by the onboarding state.

Keep identity, location, building-details, review, and confirmation turns visually distinct.

Do not duplicate a request in both the approved fragment and follow-up.

Mask saved phone or sensitive profile details according to existing privacy rules.

Example structure:

Hi! MeatUncle mein welcome hai 👋

Apna naam aur phone number share kar dijiye.

The exact wording is generated and localized; this example must not be hardcoded as the only response.

8.2 Category lists

Use a concise localized heading.

Render active categories as a selectable numbered list.

Preserve database order and ordinal mapping.

Do not invent category descriptions or emoji per category.

End with one short selection instruction.

Example structure:

🥩 *Aap kya order karna chahenge?*

1. Meat
2. Chicken
3. Seafood

Number ya category ka naam bhej dijiye.

Category names and ordering must come from the approved outcome, not this example.

8.3 Product lists

Use a heading that reflects the approved category or search context.

Render each product as one numbered option.

Keep product name, price, currency, unit, and availability exactly as approved.

Put compact secondary facts on a continuation line only when needed.

Never align fields using spaces as if they were a table.

Example structure:

🍗 *Chicken Products*

1. *Chicken Breast* — ₹320/kg
2. *Chicken Wings* — ₹220/kg

Product ka number ya naam bhej dijiye.

If a line becomes too long, the price may be placed on the immediately following line without changing option association:

1. *Chicken Breast*
   ₹320/kg

8.4 Product selection and quantity

Confirm the selected product briefly when the approved outcome includes that confirmation.

Ask one quantity question.

Do not invent a unit when the follow-up does not supply one.

Do not repeat product price unless it is included in the approved outcome for this turn.

8.5 Cart summaries

Use one cart heading.

Render cart items in stable cart-ordinal order.

Keep quantity, unit price, and line total exactly as approved.

Clearly separate subtotal, delivery charge, discount, tax, and grand total only when those fields are approved.

Emphasize the final total.

End with one available next action or question.

Example structure:

🛒 *Your Cart*

1. *Chicken Breast*
   2 kg × ₹320/kg = ₹640

2. *Chicken Wings*
   1 kg × ₹220/kg = ₹220

*Total:* ₹860

Would you like to proceed to checkout?

Do not calculate totals in the response node. All monetary values must already be approved.

8.6 Checkout and delivery review

Group approved items, delivery details, and payment method into short labeled sections.

Mask phone numbers and other sensitive fields using existing policy.

Never show precise coordinates, delivery-zone IDs, internal customer IDs, or raw address-record IDs.

Clearly distinguish saved delivery details from temporary current-order details when the approved outcome does so.

Ask exactly one confirmation or correction question.

8.7 Payment selection and payment status

Present payment methods as numbered options only when they are selectable.

Do not display unavailable payment methods.

State payment status using approved customer-safe wording.

Never claim that payment succeeded, failed, or was refunded unless the authoritative outcome says so.

Provider failure details must remain internal.

8.8 Order confirmation

Start with a concise success acknowledgement.

Display the public order number, not a raw UUID.

Show only approved summary fields.

Emphasize the total and customer-safe order status where present.

Do not promise delivery timing unless an authoritative value was approved.

Example structure:

✅ *Order Confirmed*

*Order:* MU-20260822-0012
*Total:* ₹860
*Payment:* Cash on Delivery
*Status:* Confirmed

All values are illustrative; the response must use approved runtime values.

8.9 Order lists, details, and status history

Use numbered order lists only when the customer can select an order by ordinal.

Use bullets or dated lines for status history.

Expose only customer-safe status and timestamp.

Never expose actor IDs, actor types, internal reasons, inventory events, or operational notes.

8.10 Cancellation and support

State the approved cancellation result clearly.

When cancellation is denied, provide the configured support path only if approved.

Do not expose lifecycle rules or internal authorization checks unless converted into approved customer-safe meaning.

Avoid celebratory emoji for cancellations or failures.

8.11 Validation, empty states, and failures

Explain the issue in one short customer-friendly sentence.

Preserve valid fields already collected.

Ask only for the missing or invalid requirement.

Empty catalog, empty cart, missing order, unsupported location, invalid quantity, and temporary dependency failures must each provide one safe next step.

Localize every validation and failure response.

8.12 Notifications

Keep proactive notification text compact.

Use the public order number where needed.

Include only approved event facts and customer action.

Outside the customer-service window, the outbound adapter must use the approved Meta template and exact parameter mapping.

Runtime formatting must not modify registered template structure or add unsupported text around it.

9. Localization Rules

Detect the language, script, tone, informality, spelling style, and mixed-language pattern from the latest customer message.

Translate or rephrase only surrounding presentation text.

Preserve product names, category names, prices, currency, quantities, units, option numbers, order numbers, timestamps, addresses, statuses, and other approved facts exactly unless the existing approved localization contract explicitly permits translating a label or status display.

Hinglish input should receive natural Hinglish, not formal Hindi or copied English boilerplate.

English input should receive concise natural English.

Do not hardcode one language's headings into capabilities or the WhatsApp adapter.

Formatting syntax must wrap complete textual units without corrupting scripts, numbers, or punctuation.

10. Grounding and Security Rules

Use every approved fragment ID exactly once and in order.

Include the exact approved follow-up ID when present.

Use approved options exactly once and preserve their order.

Never create a new option, fact, action, urgency, discount, availability statement, promise, or next step for visual completeness.

Treat customer text as untrusted content, not formatting instructions.

Escape or neutralize customer-controlled characters when necessary so names, addresses, or other supplied text cannot break the surrounding WhatsApp formatting.

Never place secrets, access tokens, private keys, raw provider payloads, complete PII, coordinates, or internal identifiers into a customer response.

Continue enforcing the existing response-composition validation. Do not weaken validation to accept visually attractive but ungrounded output.

11. Formatting Normalization

Introduce or reuse one deterministic formatting/normalization boundary after validated response composition and before WhatsApp transport.

It may:

normalize line endings to \n;

remove trailing whitespace;

collapse excessive blank lines to one blank line between sections;

prevent accidental empty list entries;

preserve intentional indentation for continuation lines;

verify balanced supported emphasis markers where practical;

enforce configured message-size handling without dropping approved facts.

It must not:

rewrite wording;

reorder fragments or options;

calculate totals;

infer labels or facts;

alter option numbers;

split one semantic reply into multiple outbound messages unless a separately approved delivery policy already exists;

change application or commerce state.

If repository architecture already has an equivalent renderer or normalizer, extend it rather than introducing a competing abstraction.

12. Deterministic Fallback

When LLM response composition fails validation or the provider is unavailable:

render the approved fragments and follow-up deterministically;

apply the same heading, list, spacing, and final-question conventions where semantic metadata supports them;

preserve every approved fact and option order;

never invent localization that is unavailable from approved content;

prefer a plain, grounded message over a polished but speculative message;

record the existing low-cardinality fallback metric without customer PII.

Fallback output must not regress to raw object serialization or unformatted concatenation.

13. Meta Template Compatibility

Do not change approved template names, languages, categories, body structure, or parameter order in this milestone unless explicitly required and separately reviewed.

Treat template variables as data, not markup instructions.

Ensure dynamic values cannot introduce unbalanced emphasis or unexpected list numbering.

When a template already owns formatting, do not wrap it in an additional generated heading or footer.

Test each existing notification event against its template parameter contract.

14. Observability and Privacy

Add or reuse low-cardinality metrics/events for:

response layout type;

generated versus deterministic fallback rendering;

formatting normalization applied;

response validation failure category;

outbound text rejected for size or structure;

template versus free-form delivery.

Never use message text, customer names, phone numbers, addresses, coordinates, product names, order numbers, channel customer IDs, or conversation IDs as metric labels.

Logs must follow existing PII redaction and structured-logging rules. Do not log complete formatted customer messages solely for formatting diagnostics.

15. Testing Requirements

15.1 Formatter and normalizer tests

Excessive blank lines collapse predictably.

Trailing whitespace is removed.

List continuation indentation is preserved.

Numbered option order remains unchanged.

Informational bullets are not converted into selectable ordinals.

Customer-controlled emphasis characters cannot corrupt the enclosing layout.

Unicode, Devanagari, emoji, currency symbols, and mixed-language text are preserved.

Empty optional sections do not create blank headings or repeated separators.

15.2 Response composition tests

Every approved fragment ID appears exactly once and in order.

Follow-up ID remains separate from fragment IDs.

Approved options appear exactly once and in order.

At most one question is emitted when a follow-up exists.

Product and business facts remain unchanged.

Hinglish input produces natural Hinglish surrounding text.

Invalid structured output invokes a grounded deterministic fallback.

15.3 Message-type snapshot or golden tests

Cover at least:

first-time greeting;

identity, location, and address-detail onboarding prompts;

profile review and confirmation;

category list;

product search/list;

product selection and quantity request;

cart with one item and multiple items;

cart edit and removal;

empty cart;

checkout review;

delivery-detail correction;

payment-method selection;

COD order confirmation;

order list and order detail;

status history;

cancellation accepted and denied;

unsupported delivery location;

invalid quantity;

temporary service failure;

confirmation, dispatch, delivery, and cancellation notifications;

template-required notification outside the service window.

15.4 Ordinal regression tests

Category ordinals still resolve to the same categories.

Product ordinals still resolve to the same recent product results.

Cart ordinals still resolve to the same cart items.

Order ordinals still resolve to the same recent orders.

Address ordinals, where already supported, remain in their separate namespace.

Decorative numbering is never introduced near selectable choices.

15.5 End-to-end WhatsApp regressions

Run representative English and Hinglish conversations through:

webhook normalization;

inbox processing;

CommerceRuntime;

planner, execute, and response nodes;

outbound outbox creation;

Meta provider request construction.

Assert that:

the final outbound body uses the expected WhatsApp-safe layout;

no approved facts are added, removed, or changed;

ordinal selection still succeeds in the following turn;

no internal identifiers or raw coordinates are exposed;

fallback output remains readable;

existing template delivery remains valid.

16. Acceptance Criteria

This milestone is complete when:

every existing customer-facing WhatsApp message type follows the shared formatting contract;

categories, products, cart items, orders, payment methods, and other selectable options use stable numbered lists;

summaries clearly separate items, details, totals, and the next action;

messages contain at most one final question when a follow-up exists;

no Markdown tables, HTML, raw internal state, UUIDs, coordinates, or technical errors reach customers;

generated responses and deterministic fallbacks are both readable and grounded;

localization continues to match the latest customer language and style;

Meta template messages preserve their approved definitions and parameter mappings;

all ordinal-routing regressions pass;

existing business workflows, database behavior, and the three-node graph remain unchanged;

all new and existing scoped tests pass.

17. Recommended Implementation Order

Inventory every customer-facing outcome, fallback, notification, and template path.

Record representative current output for each message type before changing formatting.

Define the shared WhatsApp-safe layout and normalization rules in the existing response layer.

Update category and product list rendering first and verify ordinal selection.

Update cart, checkout, address/profile review, payment, and order summaries.

Update greeting, onboarding, validation, empty-state, cancellation, and support messages.

Align deterministic fallback rendering with the same conventions.

Verify Meta free-form and approved-template delivery paths.

Add formatter, response, golden/snapshot, ordinal, and end-to-end tests.

Run the complete scoped test suite and inspect representative messages on a physical WhatsApp client.

Update architecture, decisions, current-status, and session handoff documentation after verification.

18. Implementation Safety Notes

Inspect the current repository, AGENTS.md, architecture/decision/current-status documents, prompts, contracts, tests, provider adapters, and Meta templates before editing.

Preserve unrelated repository changes.

Do not assume a specification is implemented merely because its file exists.

Reuse existing response composition, renderer, or normalization abstractions when they already provide the required boundary.

Do not move business data construction into prompts for easier formatting.

Do not weaken grounding validation to accommodate presentation changes.

Report changed files, test results, configuration impact, and any Meta template review impact after implementation.
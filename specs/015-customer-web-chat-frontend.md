Customer Web Chat Frontend Specification

1. Purpose

Provide a responsive browser-based chat interface for customers to use the existingAI Commerce Agent without depending on WhatsApp or another external channel.

The frontend is a thin channel adapter. It submits customer text to the existingPOST /chat endpoint, retains the returned conversation_id, and displays thebackend-approved reply. Commerce decisions, product data, cart state, checkout,orders, localization, and business validation remain owned by the backend.

2. Frozen Architecture

The commerce graph remains unchanged:

Planner -> Execute -> Response -> END

The web channel surrounds that runtime:

Browser UI
    -> POST /chat
    -> CommerceRuntime
    -> Planner -> Execute -> Response
    -> { conversation_id, reply }
    -> Browser UI

Rules:

Do not add a web-specific LangGraph node or commerce capability.

Do not reproduce planner routing or business rules in React.

Do not calculate prices, totals, availability, cart state, or order state in thebrowser.

Treat backend reply as the complete approved customer-facing response.

Keep the current REST contract backward compatible.

The initial frontend is customer chat only; staff and administration interfaces areseparate milestones.

3. Technology

React

TypeScript with strict checking

Vite

Native fetch

Plain CSS

Browser localStorage for development conversation continuity

Do not add state-management, routing, component-library, or data-fetching dependenciesunless a later requirement makes them necessary.

4. Scope

4.1 Included

Responsive customer chat interface.

Text message submission.

Rendering multiline and Unicode backend responses.

Conversation continuity using conversation_id.

Visible local transcript retention after refresh.

Loading/typing state.

Request failure display and manual retry.

New-conversation action with confirmation.

Optional development-only customer identifier header.

Keyboard and basic screen-reader accessibility.

Environment-based backend URL.

Local-development CORS documentation.

Unit and integration tests for critical behavior.

Production build output.

4.2 Excluded

Product cards, images, or a separately fetched catalog.

Client-side cart or checkout state.

Staff login, fulfilment dashboard, inventory management, or order administration.

Customer OTP authentication.

Online payment UI.

File, image, audio, voice-note, camera, or location messages.

WebSocket, Server-Sent Events, or token streaming.

Push notifications.

Rendering arbitrary HTML supplied by the backend.

Treating browser storage as authoritative business persistence.

5. API Contract

5.1 Request

POST /chat
Content-Type: application/json
X-Request-Id: <browser-generated UUID>

{
  "message": "Mujhe chicken breast chahiye",
  "conversation_id": null
}

Fields:

Field

Type

Rules

message

string

Trimmed, non-empty, maximum 2,000 characters

conversation_id

UUID string or null

null begins a new backend conversation

For subsequent turns, send the last successful response's identifier:

{
  "message": "5 kg add kar do",
  "conversation_id": "9a498390-4f75-4e24-a249-a51d28bf37ac"
}

`X-Request-Id` identifies one logical browser message. It is optional for
backward compatibility, but the frontend always supplies it and reuses the same
value for manual retry. A completed duplicate returns the stored response. A
conflicting, active, or ambiguous reuse returns a safe HTTP 409 and never
re-executes the graph automatically.

5.2 Response

{
  "conversation_id": "9a498390-4f75-4e24-a249-a51d28bf37ac",
  "reply": "Available products:\n\n1. Chicken Breast - ₹320.00/kg"
}

The frontend must reject the response as invalid when:

the payload is not a JSON object;

conversation_id is missing, empty, or not a string; or

reply is missing or not a string.

The frontend must not infer a reply from other response fields.

5.3 Development customer identity

When explicitly enabled through:

VITE_ENABLE_DEV_CUSTOMER_HEADER=true

the frontend may send:

X-Dev-Customer-Id: <browser-generated UUID>

Rules:

The header is for the environment-gated REST development adapter only.

It is not authentication or verified identity.

It must be disabled in production unless a trusted production identity boundary isimplemented.

The backend must ignore or reject this header outside its configured developmentmode.

The legacy `X-Development-Customer-Id` spelling remains accepted temporarily.
If both spellings are supplied with different normalized values, reject the
request.

6. Configuration

Provide .env.example:

VITE_CHAT_API_URL=http://localhost:8000/chat
VITE_ENABLE_DEV_CUSTOMER_HEADER=true

Rules:

Do not put secrets in VITE_* settings because Vite exposes them to the browser.

Do not place database, Gemini, Twilio, staff, or payment credentials in frontendconfiguration.

Production builds must use the deployment-specific HTTPS API URL.

Validate only public configuration in the browser.

7. User Interface Requirements

7.1 Header

Show:

business/assistant name;

a simple availability indicator;

a New chat action; and

a subtle indication when a backend conversation has been established.

The availability indicator is interface copy only unless it is later connected to areal health endpoint. It must not claim that staff, inventory, or delivery services areonline.

7.2 Conversation area

Distinguish customer and assistant messages visually.

Preserve line breaks with safe text rendering.

Never render backend reply through raw HTML injection.

Render Unicode and mixed-language text without transformation.

Display local timestamps as presentation metadata only.

Scroll to the latest message after a new message or reply.

Keep readable line lengths on desktop and mobile.

Announce new messages through an appropriate aria-live region.

7.3 Composer

Provide a labelled multiline text input.

Enter sends the message.

Shift + Enter inserts a newline.

Disable submission for empty input and while a request is in flight.

Enforce the 2,000-character browser limit while the backend independently enforcesits own request limit.

Clear the input when submission begins.

Refocus the input after completion where appropriate.

7.4 Loading behavior

While waiting for /chat:

show the customer message immediately;

show an assistant typing/loading indicator;

prevent duplicate submission from repeated clicks or key presses; and

retain the currently known conversation_id without modification.

Do not show a fabricated assistant message during loading.

7.5 New conversation

The New chat action must require confirmation because it clears the visible localtranscript.

On confirmation:

remove the stored conversation_id;

clear the local transcript;

display the static welcome message;

retain the development customer identifier; and

send conversation_id: null on the next customer message.

This action does not delete backend conversation, customer, cart, order, or audit data.

8. Browser State

Use these local keys:

Key

Purpose

commerce_conversation_id

Active backend conversation identifier

commerce_chat_transcript

Visible local customer/assistant messages

commerce_dev_customer_id

Stable development-browser identity

Rules:

Browser state improves interface continuity but is not authoritative commerce data.

Validate parsed transcript data before rendering it.

Recover safely from missing, malformed, or unavailable localStorage.

Persist only the minimal displayed transcript and identifiers.

Do not store checkout delivery details, phone numbers, addresses, payment data,tokens, credentials, internal outcomes, or capability arguments as separate browserrecords.

If a user includes personal data in chat text, it may exist in the visible transcript;a later privacy milestone must define retention and explicit clearing behavior.

9. Failure Handling

Map failures into concise customer-safe UI messages:

Condition

UI behavior

Network connection failure

State that the chat service could not be reached

HTTP 4xx

State that the message could not be sent

HTTP 5xx

State that the service is temporarily unavailable

Invalid JSON or response contract

State that an invalid response was returned

On failure:

mark the attempted customer message as not sent;

retain the failed text for a manual retry button;

do not append a fabricated assistant reply;

do not replace the existing conversation_id;

do not retry automatically, because the backend result may be ambiguous; and

disable retry while another request is active.

The backend must provide request idempotency for side-effecting operations. Browser UIguards alone cannot guarantee exactly-once execution.

10. Ordering and Concurrency

The initial frontend supports one request in flight per browser tab.

Disable the composer send action until the active request completes.

Append the backend reply after the customer message that initiated it.

Do not allow two responses to race and overwrite the conversation identifier.

Multiple browser tabs remain separate UI instances and may share local storage; thebackend remains responsible for conversation locking and durable idempotency.

11. Backend CORS

For local development, FastAPI must allow the Vite origin:

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Request-Id", "X-Dev-Customer-Id",
                   "X-Development-Customer-Id"],
)

Production rules:

Configure an explicit HTTPS frontend origin.

Do not reflect arbitrary origins.

Do not use wildcard origins with credentialed requests.

Permit only methods and headers required by the chat contract.

CORS is a browser control, not authentication or authorization.

12. Security and Privacy

Render all message content as text, not HTML.

Do not expose backend stack traces or raw error bodies.

Do not log full conversations in browser console output.

Do not include secrets in source code, .env files shipped to the browser, buildoutput, or request headers.

Use HTTPS in production.

Add a restrictive Content Security Policy at the hosting boundary.

Add X-Content-Type-Options, referrer, framing, and permissions policies at thehosting boundary.

Rate limiting and abuse protection remain backend responsibilities.

The development customer ID must never be presented as verified phone ownership.

13. Accessibility

All controls must be keyboard operable.

Provide visible focus styles.

Associate accessible labels with the composer and icon-only send button.

Use semantic buttons rather than clickable generic elements.

The new-chat confirmation must use dialog semantics.

Text and controls must meet WCAG AA contrast targets.

Respect browser zoom and remain usable at a 320-pixel viewport width.

Do not rely on colour alone to communicate failed or active state.

14. Responsive Behavior

Support mobile widths from 320 pixels.

Use the available viewport without horizontal scrolling.

Keep the composer reachable when the on-screen keyboard is open where supported.

Use a centred bounded chat card on larger displays.

Adapt header spacing and labels on narrow screens.

Preserve touch targets of approximately 44 by 44 CSS pixels for primary controls.

15. Suggested Project Structure

frontend/
├── src/
│   ├── App.tsx
│   ├── api.ts
│   ├── main.tsx
│   ├── storage.ts
│   ├── styles.css
│   ├── types.ts
│   └── vite-env.d.ts
├── .env.example
├── .gitignore
├── index.html
├── package.json
├── README.md
├── tsconfig.app.json
├── tsconfig.json
├── tsconfig.node.json
└── vite.config.ts

Responsibilities:

App.tsx: UI state and customer interaction.

api.ts: /chat transport and response validation.

storage.ts: safe browser-storage access.

types.ts: frontend-only transport and presentation types.

styles.css: responsive and accessible presentation.

Do not import backend Python models into the frontend. Keep the JSON transport contractsmall and explicit.

16. Testing Strategy

16.1 Unit tests

Test:

valid and invalid ChatResponse validation;

safe storage loading with malformed JSON;

conversation and transcript clearing;

customer ID stability;

empty-message prevention;

Enter versus Shift+Enter behavior; and

error-message mapping.

16.2 Component tests

Test:

welcome state;

sending and typing state;

successful reply rendering;

multiline and Hinglish response rendering;

failed-message display and retry;

new-chat confirmation and cancellation;

conversation-saved indicator; and

keyboard-accessible controls.

16.3 API integration tests

With a mocked server, verify:

first request sends conversation_id: null;

subsequent request sends the returned identifier;

development header is sent only when enabled;

4xx, 5xx, network, invalid JSON, and invalid-schema responses are handled safely;and

one request is submitted for one user action.

16.4 Backend end-to-end test

Against a test FastAPI instance:

open a fresh frontend session;

send Mujhe chicken breast chahiye;

receive and save a non-empty conversation_id;

render the localized backend reply;

send a second turn with the same conversation identifier; and

verify that the backend continues the same commerce session.

External Twilio access is not required for this test.

17. Build and Run

Local development:

cp .env.example .env
npm install
npm run dev

Production validation:

npm run build
npm run preview

The build must fail on TypeScript errors. Generated dist/, dependency directories,local .env, and TypeScript build metadata must not be committed unless deploymentpolicy explicitly requires build artifacts.

18. Acceptance Criteria

This milestone is complete when:

A customer can send a non-empty text message from desktop and mobile layouts.

The frontend sends the exact POST /chat request contract.

The returned conversation_id is used for subsequent messages.

The backend reply is rendered safely with its Unicode text and line breaks.

Refreshing the page restores the active local transcript and conversation ID.

Starting a new chat clears only local conversation presentation state.

Loading state prevents duplicate active submissions.

Network, HTTP, JSON, and contract errors produce safe feedback and manual retry.

The development customer header is environment-gated and disabled for production.

No product, pricing, cart, checkout, order, or localization logic is duplicated inthe frontend.

The UI is keyboard usable and responsive down to 320 pixels.

npm run build completes successfully.

Automated tests cover the critical conversation, storage, retry, and API-contractbehavior.

19. Deferred Extensions

Authenticated customer accounts and OTP verification.

Server-backed conversation-list and transcript history.

Structured response blocks or product cards backed by an explicit versioned API.

Online payment redirect/return UI.

Order tracking page.

Browser notifications.

Voice and media messages.

Streaming responses.

Human-agent handoff.

Staff fulfilment frontend.

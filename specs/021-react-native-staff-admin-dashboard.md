React Native Staff and Admin Dashboard Specification

1. Purpose

Build one Android-first React Native mobile application for fulfilment staff andadministrators to operate customer orders through the authenticated APIs defined in020-authenticated-staff-fulfilment-api.md.

The application provides role-aware screens for:

Staff login
    -> fulfilment overview
    -> order queue
    -> order details
    -> valid status transition
    -> refreshed order state

Administrators use the same application and receive additional controls permitted bythe backend, initially eligible order cancellation. The backend remains authoritativefor identity, permissions, tenant isolation, order state, inventory effects,idempotency, and audit history.

The first release is built, tested, and distributed for Android. The source remainscross-platform so an iOS release can be added later without rebuilding the applicationarchitecture.

2. Prerequisites

Authenticated staff fulfilment API from specification 020.

Order and inventory lifecycle from specification 006.

Customer order notifications from specification 019.

A development and staging backend reachable from physical Android devices.

HTTPS for every non-local environment.

At least one bootstrapped ADMIN account and one FULFILMENT_STAFF account foracceptance testing.

3. Goals

Provide one secure mobile application for both supported staff roles.

Let staff see actionable orders quickly and safely advance fulfilment.

Let admins perform their additional permitted actions without creating a separateapplication.

Display only actions currently permitted by the backend response.

Handle stale order versions, duplicate taps, network interruption, and retries safely.

Protect customer delivery information on the device.

Keep the application usable on common Android phone sizes and unstable mobilenetworks.

Preserve an iOS-compatible codebase without making App Store delivery part of thismilestone.

Keep all commerce decisions outside the mobile application.

4. Non-goals

Customer shopping, cart, checkout, or customer account screens.

Customer OTP or staff OTP authentication.

Public staff registration or password recovery.

Creating staff accounts or changing roles in the first mobile release.

A web-based admin dashboard.

Online payment capture, refunds, or payment-provider administration.

Inventory adjustments, purchase orders, stock counts, or warehouse management.

Driver assignment, navigation, live location, route optimization, or proof ofdelivery.

Push notifications, background synchronization, or silent background order updates.

Full offline fulfilment mutations.

Embedding an LLM, planner, LangGraph runtime, or prompt logic in the app.

iOS App Store submission in the first release.

5. Technology Decisions

Use:

React Native with Expo and TypeScript.

The stable Expo SDK supported at implementation time; pin the selected version in thelockfile.

Expo Router for file-based navigation.

TanStack Query for server-state fetching, caching, invalidation, and request status.

React Hook Form with Zod for client-side form parsing and validation.

Expo SecureStore for the short-lived access token.

The native fetch API behind a typed application API client unless repositoryconstraints justify another HTTP library.

Jest and React Native Testing Library for unit/component tests.

Maestro or an equivalent Android-capable runner for critical end-to-end flows.

EAS development/preview builds or local Android builds for APK distribution.

Do not add Redux for the first version. Authentication lifecycle and small UI-onlystate can use focused React context/state; authoritative server state belongs inTanStack Query.

Do not copy generated backend models manually across many files. Define a small,mobile-owned API contract layer and, when the backend exposes stable OpenAPI, prefer arepeatable typed-client generation step with reviewed output.

6. Frozen Boundaries

React Native UI
    -> typed API client
    -> authenticated staff REST API
    -> existing backend services and PostgreSQL

Rules:

The mobile app never connects directly to PostgreSQL.

The app never calls customer /chat, planner, capability, or LangGraph endpoints.

The app never decides whether an order transition is valid.

Hiding a button is user experience, not authorization. The backend must reject everyunauthorized action independently.

The app never supplies trusted staff_id, role, actor_id, or tenant_id valuesin mutation bodies.

Customer notifications are produced by the backend transaction/outbox fromspecification 019, not by the app.

Inventory mutation and status-history creation remain backend responsibilities.

The order version and Idempotency-Key contract from specification 020 is requiredfor every status mutation.

7. Application Roles

7.1 FULFILMENT_STAFF

May:

log in and view their identity;

see orders belonging to their active tenant;

filter and inspect orders;

advance an order through transitions authorized by the backend;

view delivery details necessary to fulfil an individual order;

view staff-visible status history.

May not:

cancel an order;

create staff accounts;

change roles or tenant memberships;

override a rejected transition;

modify prices, quantities, addresses, payment state, or inventory directly.

7.2 ADMIN

Has the same operational access and may additionally:

cancel an eligible order with a required reason;

see admin-only operational actions explicitly returned by the backend.

This milestone does not add mobile staff-account management even for admins.

8. Navigation Structure

Use protected and public route groups:

app/
  _layout.tsx
  (public)/
    login.tsx
  (protected)/
    _layout.tsx
    dashboard.tsx
    orders/
      index.tsx
      [orderId].tsx
    account.tsx

Recommended navigation:

Authentication stack for signed-out users.

Protected stack for signed-in users.

Bottom navigation with Dashboard, Orders, and Account where it improves commonAndroid ergonomics.

Order details open as a pushed screen so Android back navigation returns to thepreserved order list and filters.

Navigation guards must wait until SecureStore token restoration and /me validationfinish. Do not briefly render protected content before authentication is known.

9. Screens and User Flows

9.1 Application launch

Show a neutral launch/loading state.

Read the access token from SecureStore.

If absent, route to login.

If present, call GET /api/staff/v1/me.

If valid, initialize the protected application with the returned identity and role.

If expired or invalid, delete the token and route to login.

If the network is temporarily unavailable, show a retryable connection state; nevertreat an unvalidated token as an authenticated session.

9.2 Login

Fields:

email;

password;

password visibility toggle;

submit button.

Behavior:

Normalize only safe presentation whitespace locally; the backend remainsauthoritative for identity normalization.

Disable duplicate submission while one login is pending.

Show a generic invalid-credentials message for wrong email, wrong password, disabledaccount, or other backend responses intentionally mapped to that category.

Do not reveal whether an email exists.

Save only the successful access token in SecureStore.

Immediately call /me after saving; if identity initialization fails, remove thetoken and return to login.

Never save the password, include it in logs, or keep it after the login screenunmounts.

9.3 Fulfilment dashboard

Show operational summary cards using backend-supported counts:

Confirmed
Preparing
Out for delivery
Needs attention (only if defined by the backend)

The dashboard also shows short actionable queues, such as the oldest confirmed orders.Selecting a card opens the order list with the matching filter.

If specification 020 does not yet expose an aggregate endpoint, use bounded parallelorder-list requests only for the first small deployment. Before production scale, adda tenant-scoped backend summary endpoint:

GET /api/staff/v1/dashboard/summary

Do not download all orders to calculate counts on the device.

9.4 Order list

Each row displays:

order reference
current status
customer name
masked phone number
order total and currency
created/updated time

Functions:

status filter;

exact order-reference search;

bounded date-range filter;

pull to refresh;

cursor-based infinite scrolling;

empty, initial-loading, next-page-loading, error, and retry states;

clear filters;

navigate to individual order details.

Rules:

Preserve filters and scroll position when returning from details.

Debounce order-reference input.

Cancel or ignore obsolete requests when filters change.

Prevent duplicate cursor-page insertion.

Do not expose full phone or address in list rows.

9.5 Order details

Display:

order reference and current status;

payment method and relevant payment state;

immutable item snapshots with quantity, unit, unit price, and total;

order total and currency;

customer name;

full phone number and delivery address, because the authenticated user opened anindividual fulfilment record;

customer-safe fulfilment timeline plus permitted staff audit information;

last updated time;

valid actions returned by the backend;

a manual refresh action.

PII behavior:

Do not place full delivery details in navigation parameters, analytics, crash-reportbreadcrumbs, notification payloads, or persistent query storage.

Clear order-detail query data on logout.

Consider Android screen-capture blocking for order-detail screens as a configurableproduction hardening option; it is not required for local development.

9.6 Advance status

Examples:

CONFIRMED -> Mark as preparing
PREPARING -> Mark as out for delivery
OUT_FOR_DELIVERY -> Mark as delivered

Flow:

Show only actions included in the current order response.

Require an explicit confirmation sheet/dialog naming the target status.

Generate one client idempotency key for the user's logical action.

Send the current version in If-Match and the key in Idempotency-Key.

Disable all mutation controls while that logical request is unresolved.

On success, replace the cached order with the response and invalidate affected listand dashboard queries.

Announce success accessibly and show the new status.

Reuse the same idempotency key if transport failure leaves the outcome unknown andthe user chooses retry.

Do not optimistically display a new authoritative order status before the serverconfirms it. A temporary pending indicator is allowed.

9.7 Admin cancellation

Show cancellation only when both are true:

/me identifies an ADMIN role for the active tenant; and

the order response lists cancellation as currently allowed.

Flow:

Open a destructive-action confirmation sheet.

Require a non-empty cancellation reason.

Explain that cancellation may release reserved inventory and notify the customer.

Generate and retain an idempotency key for the logical cancellation.

Submit target_status = CANCELLED, the reason, and current version.

On success, refresh order, lists, and summary.

The app must still handle 403, 409 invalid_transition, and stale-version responsesbecause permissions or order state may change after rendering.

9.8 Account and logout

Display:

staff display name;

role;

active tenant label if the backend safely provides one;

application version/build number;

logout action.

Logout must:

remove the access token from SecureStore;

clear authentication state;

clear all TanStack Query caches, including customer PII;

clear retained idempotency retry state;

reset navigation so Android back cannot reopen protected screens.

10. API Contracts Used

The app consumes the endpoints from specification 020:

POST  /api/staff/v1/auth/login
GET   /api/staff/v1/me
GET   /api/staff/v1/orders
GET   /api/staff/v1/orders/{order_id}
PATCH /api/staff/v1/orders/{order_id}/status

Recommended bounded summary addition:

GET /api/staff/v1/dashboard/summary

The API client must:

use one configured base URL;

add Authorization: Bearer <token> only to authenticated staff endpoints;

add a safe application version header;

use request timeouts and cancellation;

parse response bodies with runtime schemas before exposing them to screens;

map backend error codes to typed application errors;

never retry non-idempotent mutations automatically with a new idempotency key;

never log authorization headers or unredacted response bodies.

11. Mobile Models

Define only presentation/API contracts needed by the app:

type StaffRole = "ADMIN" | "FULFILMENT_STAFF";

type OrderStatus =
  | "CONFIRMED"
  | "PREPARING"
  | "OUT_FOR_DELIVERY"
  | "DELIVERED"
  | "CANCELLED";

type PermittedOrderAction = {
  targetStatus: OrderStatus;
  requiresReason: boolean;
};

type StaffIdentity = {
  staffId: string;
  displayName: string;
  tenantId: string;
  role: StaffRole;
};

The exact wire-field casing must match the backend OpenAPI contract. Runtime parsingmust reject unknown critical enum values safely and display a refresh/update-requiredstate rather than guessing behavior.

12. State Ownership

12.1 Persisted securely

Access token only, using SecureStore.

12.2 Memory-only application state

Validated current staff identity.

Active list filters.

UI state such as open confirmation sheets.

In-flight logical mutation key and retry decision.

12.3 TanStack Query server state

Dashboard summary.

Order pages.

Individual order details.

Do not persist the Query cache to AsyncStorage in the first version because it containscustomer and delivery information. Do not use AsyncStorage for access tokens.

13. Authentication Lifecycle

SecureStore is a storage boundary, not proof that the token remains valid.

Validate the restored token through /me on each cold application start.

A 401 invalid_access_token from any authenticated request triggers a single globalsession-expired flow.

Coordinate concurrent 401 responses so the user sees one logout/session-expiredtransition rather than several dialogs.

Since specification 020 has no refresh tokens, do not implement silent refresh.

After expiry, clear secure and in-memory state and ask the staff member to log inagain.

A 403 staff_access_denied does not always mean the token is invalid; show an accesserror, refresh /me, and remove the session if membership is no longer active.

14. Idempotency and Ambiguous Results

Generate UUID idempotency keys with a secure native random UUID source.

For each logical mutation, retain in memory:

idempotency key
order ID
expected version
target status
reason hash or exact in-memory request
attempt state

Rules:

Duplicate taps share one logical request and key.

A timeout, connection reset, or application-level unknown result does not prove thetransition failed.

A user-triggered retry of the same logical action reuses the same key and payload.

A changed target, reason, order, or version is a new action and receives a new key.

Never reuse a key across different orders or inputs.

After a cold app termination loses memory-only retry state, refresh the order beforeoffering another mutation. The backend's order state is authoritative.

15. Concurrency and Conflict UX

When the backend returns 409 stale_order_version:

Do not automatically overwrite or resubmit.

Fetch the latest order.

Explain that another staff member updated it.

Show the latest status.

Recalculate visible actions from the fresh server response.

Require a new explicit confirmation for any still-valid action.

When the backend returns 409 invalid_transition, refresh the order and show that therequested action is no longer available.

When the backend returns 409 idempotency_key_conflict, stop retrying that request,refresh the order, record a safe operational error, and require a new user action.

16. Network and Error Experience

Separate:

initial loading;

empty result;

offline/unreachable backend;

request timeout;

unauthenticated session;

unauthorized operation;

stale data conflict;

validation error;

temporary server failure;

unexpected response contract.

Rules:

Preserve already rendered non-stale list data during background refresh errors.

Never show raw stack traces, SQL errors, JWT details, HTML gateway responses, or fullprovider payloads.

Use the backend's stable error code; treat message as safe display text only whenthe API contract marks it customer/staff-safe.

Provide retry for safe queries.

For mutations, retry only through the idempotency rules above.

Show a persistent offline banner when network state is unavailable, but verify actualrequest errors because connectivity indicators can be inaccurate.

17. Android-First Requirements

Support the Android API range selected by the stable Expo SDK and document the actualminimum version in the implementation README.

Test on at least one small phone, one common mid-size phone, and one recent Androidversion.

Handle Android hardware back correctly for dialogs, details, protected navigation,and logout.

Handle software keyboard avoidance on login and cancellation forms.

Respect safe areas, font scaling, light/dark system themes, and touch target sizes.

Produce a signed preview APK for internal testing; production Play Store AAB andpublishing are separate release work.

Use a distinct Android application ID for development/staging and production.

Do not permit cleartext HTTP outside an explicitly isolated local-development build.

18. iOS Compatibility

The source must avoid unnecessary Android-only assumptions:

use cross-platform Expo modules where practical;

isolate unavoidable platform-specific code behind small adapters;

avoid hard-coded Android dimensions and back behavior in shared business/UI logic;

keep icons, safe areas, keyboard handling, and permissions portable;

keep an iOS bundle identifier reserved in configuration.

iOS device testing, certificates, provisioning profiles, TestFlight, App Store privacyforms, and App Store submission are deferred.

19. Design System and Accessibility

Create a small internal design system containing:

color tokens, typography, spacing, radii, and elevation;

buttons including primary, secondary, and destructive variants;

form fields and validation messages;

status badges with text labels as well as color;

cards, list rows, skeletons, empty states, banners, and confirmation sheets;

accessible loading and error announcements.

Requirements:

Meet WCAG AA contrast where applicable.

Do not communicate order status using color alone.

Support system font scaling without hiding critical actions.

Provide accessible labels/hints for icon-only controls.

Use minimum practical touch targets of approximately 44x44 points/density-independentpixels.

Keep confirmation wording explicit, for example Mark MU-2026-000123 as preparing?.

Use locale-aware display formatting for dates and money while preserving authoritativecurrency and numeric meaning.

The first UI language may be English for internal staff. Localization infrastructuremay be added later when actual staff-language requirements are known.

20. Security and Privacy

Store access tokens only in SecureStore.

Never persist passwords, customer addresses, order payloads, or full phone numbers inAsyncStorage.

Remove all protected caches and secrets on logout.

Redact authorization headers, passwords, delivery details, and full API bodies fromlogging and crash reporting.

Do not use third-party analytics that record screen text or automatic screenshots.

Disable development menus, verbose network logging, and mock endpoints in productionbuilds.

Use HTTPS and validate the platform trust chain. Certificate pinning is deferred untiloperational rotation and failure-recovery procedures are designed.

Keep API URLs and non-secret feature flags in Expo public configuration; never placesigning secrets, database credentials, backend private keys, or privileged API tokensin the app bundle.

Treat every value bundled in a mobile application as publicly recoverable.

Add inactivity relock later if required by production risk assessment; short backendaccess-token expiry is the first boundary.

21. Configuration and Environments

Support at least:

development
staging
production

Environment-specific configuration includes:

EXPO_PUBLIC_API_BASE_URL
EXPO_PUBLIC_APP_ENV
EXPO_PUBLIC_REQUEST_TIMEOUT_MS

Rules:

Only values prefixed/public by design may enter the application bundle.

Validate configuration during application startup and fail with a safe configurationscreen in non-production builds.

Production builds must not silently fall back to localhost, staging, or a default APIURL.

Use separate Android application IDs and visible app names for non-production builds.

Commit example configuration without credentials; keep real local environment filesout of source control.

22. Suggested Project Structure

staff-mobile/
  app/
    _layout.tsx
    (public)/
      login.tsx
    (protected)/
      _layout.tsx
      dashboard.tsx
      orders/
        index.tsx
        [orderId].tsx
      account.tsx
  src/
    api/
      client.ts
      contracts.ts
      errors.ts
      staff-auth-api.ts
      staff-orders-api.ts
    auth/
      auth-context.tsx
      secure-token-store.ts
      session-controller.ts
    components/
      design-system/
      orders/
    features/
      dashboard/
      orders/
    hooks/
    query/
      query-client.ts
      query-keys.ts
    validation/
    config/
    observability/
    test/
  assets/
  app.config.ts
  eas.json
  package.json
  tsconfig.json

Keep route files thin. API access belongs in the API layer, query behavior in featurehooks, reusable presentation in components, and no backend business rules in screens.

23. Observability

Capture safe, low-cardinality mobile events such as:

app_started
login_succeeded / login_failed_category
orders_loaded / orders_load_failed_category
order_transition_succeeded / order_transition_failed_category
stale_order_detected
session_expired

Attach:

application version and build number;

environment;

OS/platform version;

safe backend request correlation ID when returned.

Do not attach staff email, access token, customer name, phone, address, order contents,free-form cancellation reason, idempotency key, or full order ID to third-partytelemetry. Crash reporting and remote analytics are feature-gated until privacy anddata-retention configuration is approved.

24. Testing Requirements

24.1 Unit tests

Runtime parsing of successful and invalid API payloads.

Backend error-code mapping.

Query-key construction and cursor-page merging.

Login form and cancellation-reason validation.

Permitted-action rendering from identity plus server-provided actions.

Idempotency key retention across an ambiguous retry.

Authentication/session state transitions.

24.2 Component tests

Login loading, invalid credentials, timeout, and success.

Dashboard loading, populated, empty, and failure states.

Order filters and clear-filter behavior.

Order list pagination without duplicates.

Detail rendering with item and timeline data.

Staff cannot see cancellation controls.

Admin sees cancellation only when the backend permits it.

Confirmation and destructive cancellation sheets.

Accessibility labels, scalable text, and status labels.

24.3 API integration tests

Token is attached only to protected staff requests.

401 clears one session and redirects to login.

403 does not expose or enable unauthorized operations.

Status mutation sends exact If-Match and Idempotency-Key headers.

Same logical retry sends the same key and payload.

Success invalidates dashboard, list, and detail queries.

Stale version refreshes details without automatic resubmission.

Logout clears query caches and token storage.

24.4 End-to-end Android flows

Test against a seeded staging backend:

Staff logs in, filters confirmed orders, opens one, and marks it preparing.

Staff advances preparing to out for delivery and later delivered.

Staff cannot access admin cancellation.

Admin cancels an eligible order with a reason.

A second actor updates an open order and the first actor receives stale-version UX.

Network is interrupted after mutation submission; retry uses the same logical keyand no duplicate history/notification occurs.

Token expires and protected data is cleared before returning to login.

Logout prevents Android back navigation from reopening order details.

24.5 Device verification

Small and mid-size Android displays.

Light and dark themes.

Large font setting.

Slow and interrupted network.

Cold start with valid, expired, invalid, and absent tokens.

Release/preview build, not only Expo development mode.

25. Acceptance Criteria

This milestone is complete when:

One Expo/React Native TypeScript application supports both staff roles.

A signed Android preview APK can be installed on a physical device.

Staff can authenticate and the app validates restored sessions through /me.

Staff can view tenant-scoped dashboard data, order lists, and individual orders.

Full customer delivery PII appears only on an authenticated order-detail screen andis not persisted in general device storage.

Fulfilment staff can execute permitted forward transitions but cannot cancel.

Admins can cancel only eligible orders and must supply a reason.

Every mutation uses the current order version and one retained idempotency key.

Stale concurrent updates produce a refresh-and-review experience rather than anoverwrite or automatic resubmission.

Logout and session expiry clear tokens, protected navigation, and cached PII.

Backend authorization remains effective even when mobile UI controls are bypassed.

Unit, component, API integration, Android end-to-end, accessibility, and physicaldevice checks pass.

No Planner, LangGraph, direct database, notification-provider, or commerce businesslogic is introduced into the mobile application.

The shared code remains suitable for a later iOS testing and release milestone.

26. Recommended Implementation Order

Confirm specification 020 endpoints and publish stable OpenAPI contracts.

Create staff-mobile with Expo, TypeScript, Expo Router, linting, formatting, andtests.

Add environment validation, typed API client, runtime response schemas, and typederrors.

Implement SecureStore token storage, authentication context, login, /mevalidation, session expiry, and logout.

Add the design-system primitives and protected navigation shell.

Implement order list filters, cursor pagination, refresh, and error states.

Implement order details, delivery PII presentation, history, and permitted actions.

Implement idempotent status transition and stale-version handling.

Add admin cancellation with a required reason and destructive confirmation.

Implement dashboard summary and actionable queues.

Add privacy-safe observability and production build guards.

Complete automated tests, accessibility review, physical-device verification, andsigned preview APK distribution.

27. Follow-up Milestones

After this specification:

Pilot the application with a small internal staff group and collect operationalfeedback.

Add production deployment/security hardening, secret rotation, backups, restoredrills, and incident procedures across backend and mobile release operations.

Add mobile push notifications only after defining device registration, staff topicauthorization, token lifecycle, and privacy requirements.

Add staff-account/role administration when real organizational needs are known.

Test and release iOS through TestFlight and the App Store when required.

Add the production payment-provider adapter when merchant setup exists.

Add customer OTP only when verified phone ownership becomes a product requirement.
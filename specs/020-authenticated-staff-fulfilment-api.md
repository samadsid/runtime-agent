Authenticated Staff Fulfilment API Specification

1. Purpose

Provide a secure staff-facing API for operating the fulfilment lifecycle alreadydefined in 006-order-fulfilment-inventory.md:

CONFIRMED -> PREPARING -> OUT_FOR_DELIVERY -> DELIVERED
     \-> CANCELLED (only where the existing domain policy permits it)

This milestone closes the authentication and authorization boundary that was deferredwhile the customer ordering flow was completed. Staff actions use deterministic HTTPAPIs and existing commerce services. They never pass through the customer planner orthe LLM.

Customer OTP and verified customer phone ownership remain deferred. Staffauthentication is a separate concern and must not depend on customer authentication.

2. Prerequisites

Order, order-item, inventory reservation, and status-history persistence.

Fulfilment transition rules and inventory effects from specification 006.

Customer order management and cancellation rules from specification 007.

Durable notification outbox from specification 019.

Alembic-managed PostgreSQL schema.

Existing FastAPI application/container and trusted tenant configuration.

3. Goals

Authenticate every usable staff endpoint.

Authorize actions with explicit tenant-scoped roles.

Allow staff to list, filter, inspect, and transition orders.

Reuse existing domain services and transition rules.

Prevent cross-tenant reads and writes.

Make repeated update requests safe.

Detect stale concurrent updates instead of silently overwriting them.

Attribute every fulfilment action to a durable staff identity.

Emit customer notifications through the transactional outbox.

Return stable, customer-PII-conscious API errors and operational logs.

Support a later staff dashboard without coupling the API to a specific frontend.

4. Non-goals

Customer login, customer OTP, or customer phone verification.

Social login, SSO, SAML, SCIM, or enterprise identity-provider integration.

Public staff self-registration.

Password recovery by email in the first milestone.

A staff frontend or mobile application.

Changing inventory or order transition rules defined in specification 006.

Delivery-agent assignment, route planning, live tracking, or proof of delivery.

Online payment administration or refunds.

Letting the planner, Response Node, or an LLM authorize staff operations.

5. Frozen Architecture

The customer graph remains unchanged:

Planner -> Execute -> Response -> END

The staff path is separate:

Staff client
    -> FastAPI staff route
    -> authenticate access token
    -> authorize tenant membership and permission
    -> validate request and idempotency key
    -> existing fulfilment/order service
    -> PostgreSQL transaction
         -> lock and update order
         -> apply inventory effect
         -> append order status history
         -> insert notification outbox event
         -> store idempotency result
       COMMIT
    -> return staff-safe response

Rules:

Do not add a staff or fulfilment node to LangGraph.

Staff routes never construct planner commands or invoke CommerceRuntime.chat.

Route handlers do not contain transition or inventory business logic.

Domain services do not parse JWTs or HTTP requests.

Repositories do not make authorization decisions, but every repository operation isscoped by a trusted tenant_id supplied after authentication.

PostgreSQL is authoritative for staff accounts, memberships, orders, inventory,history, idempotency records, and notification intent.

Customer notifications follow specification 019 and are never sent inline insidethe order transaction.

6. Staff Identity and Roles

6.1 Staff account

class StaffStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class StaffAccount(BaseModel):
    id: UUID
    email: str
    display_name: str
    status: StaffStatus
    created_at: datetime
    updated_at: datetime

Email addresses are normalized for identity comparison. Preserve a suitable displayform separately if required. A disabled account cannot log in, refresh a session, oruse an existing access token.

6.2 Tenant membership

One staff account may belong to more than one tenant in the future. Authorization istherefore based on a durable membership rather than a tenant ID accepted from anuntrusted request body.

class StaffRole(str, Enum):
    ADMIN = "ADMIN"
    FULFILMENT_STAFF = "FULFILMENT_STAFF"


class StaffTenantMembership(BaseModel):
    staff_id: UUID
    tenant_id: UUID
    role: StaffRole
    active: bool
    created_at: datetime

Permissions:

Operation

ADMIN

FULFILMENT_STAFF

Log in and inspect own identity

yes

yes

List and view tenant orders

yes

yes

Advance valid fulfilment status

yes

yes

Cancel where domain policy permits

yes

no

Create/disable staff accounts

later

no

Change tenant membership or role

later

no

Administrative user-management endpoints are excluded initially. The first adminaccount and membership are created through an explicit bootstrap command, not a publicHTTP route or application-startup default password.

7. Authentication Policy

7.1 Credentials

Login uses normalized email plus password.

Store only a modern adaptive password hash, using Argon2id with an establishedpassword-hashing library.

Never log, return, encrypt for recovery, or place plaintext passwords in databasefields, checkpoints, metrics, traces, or exception messages.

Apply a configurable minimum password policy at account bootstrap and future passwordchanges.

Compare credentials using the password library's safe verification operation.

7.2 Access tokens

Issue a short-lived signed JWT access token after successful login. It contains only:

iss, aud, sub, jti, iat, nbf, exp

sub is the staff account ID. Tenant and role authorization must be loaded from thecurrent database membership on each request; do not trust a long-lived role copied intothe token. This ensures disabled accounts and revoked memberships take effect withoutwaiting for all access tokens to expire.

Requirements:

Use an asymmetric signing key in production so verification does not require sharingthe private key.

Pin the accepted signing algorithm; never accept the algorithm from the token.

Validate issuer, audience, signature, expiry, not-before time, and required claims.

Keep access-token lifetime configurable and short, initially 15 minutes.

Never put email, password, customer PII, tenant secrets, or permissions in the token.

Return the token only over HTTPS outside local development.

Refresh tokens are excluded from the first version. Staff log in again after accesstoken expiry. A refresh-token lifecycle can be introduced later without weakening thisboundary.

7.3 Login abuse protection

Rate-limit login attempts by normalized account identity and source network signal.

Return the same invalid_credentials response for unknown email and wrong password.

Do not reveal whether an account exists or is disabled.

Record safe audit events for successful login, failed login, and disabled-accountattempts without recording submitted passwords or complete tokens.

Configure rate-limit storage so it works across application instances in production;an in-memory limiter is acceptable only in explicitly marked local development.

8. PostgreSQL Schema

Create all application-owned objects through Alembic.

8.1 staff_accounts

Column

Type

Rule

id

UUID

Primary key

email_normalized

text

Required and globally unique

display_name

text

Required

password_hash

text

Required; never returned

status

text

ACTIVE or DISABLED

created_at

timestamptz

Required

updated_at

timestamptz

Required

Constraints:

UNIQUE (email_normalized)
CHECK (status IN ('ACTIVE', 'DISABLED'))

8.2 staff_tenant_memberships

Column

Type

Rule

staff_id

UUID

FK to staff_accounts

tenant_id

UUID

Trusted tenant boundary

role

text

Supported staff role

active

boolean

Required

created_at

timestamptz

Required

updated_at

timestamptz

Required

Constraints:

PRIMARY KEY (staff_id, tenant_id)
CHECK (role IN ('ADMIN', 'FULFILMENT_STAFF'))
INDEX (tenant_id, active, role)

8.3 Order version

Add an integer version to orders if an equivalent concurrency field does notalready exist:

version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1)

Every successful state-changing order update increments it. Repeating an alreadycompleted idempotent request returns the stored response and does not increment it.

8.4 staff_api_idempotency

Column

Type

Rule

id

UUID

Primary key

tenant_id

UUID

Required tenant boundary

staff_id

UUID

Authenticated actor

idempotency_key

text

Required client-provided key

operation

text

Bounded operation name

request_hash

text

Hash of canonical validated business input

resource_id

UUID

Target order ID

response_status

integer

Completed HTTP status

response_body

jsonb

Completed safe response snapshot

created_at

timestamptz

Required

expires_at

timestamptz

Retention boundary

Constraints:

UNIQUE (tenant_id, staff_id, idempotency_key)
INDEX (expires_at)

The idempotency record is committed in the same transaction as the order transition,history row, inventory effect, and notification outbox record.

9. API Surface

Prefix all endpoints with /api/staff/v1.

9.1 Login

POST /api/staff/v1/auth/login
Content-Type: application/json

Request:

{
  "email": "staff@example.com",
  "password": "submitted-secret"
}

Success:

{
  "access_token": "<redacted>",
  "token_type": "Bearer",
  "expires_in": 900
}

The response must include Cache-Control: no-store and must not expose the passwordhash or account-existence details.

9.2 Current staff identity

GET /api/staff/v1/me
Authorization: Bearer <access-token>

Return staff ID, display name, and active tenant memberships/roles. Never return thepassword hash.

9.3 List orders

GET /api/staff/v1/orders
Authorization: Bearer <access-token>

Supported filters:

status: one supported order status.

created_from and created_to: bounded UTC date-time range.

order_reference: exact normalized reference search.

limit: bounded page size, default 50 and maximum 100.

cursor: opaque stable pagination cursor.

Default ordering is newest first with a deterministic ID tie-breaker. Do not implementunbounded offset pagination.

The list response contains only operationally necessary fields:

order_id, order_reference, status, payment_method, total, currency,
customer_name, masked_phone_number, created_at, updated_at, version

The tenant is derived from the authenticated membership context, not from a queryparameter accepted without authorization.

9.4 View order

GET /api/staff/v1/orders/{order_id}
Authorization: Bearer <access-token>

Return:

immutable order-item snapshots;

current order and payment method/status needed for fulfilment;

delivery name, phone, and address because authorized fulfilment requires them;

customer-safe status timeline plus staff audit fields permitted to staff;

current order version;

actions currently permitted by the domain transition policy.

Return 404 order_not_found for both a missing order and an order outside the activetenant. Do not reveal cross-tenant existence.

9.5 Transition order

PATCH /api/staff/v1/orders/{order_id}/status
Authorization: Bearer <access-token>
Idempotency-Key: <unique-client-key>
If-Match: "<current-version>"
Content-Type: application/json

Request:

{
  "target_status": "PREPARING",
  "reason": null
}

Rules:

Idempotency-Key is mandatory and validated for bounded length and allowedcharacters.

If-Match is mandatory for a new mutation.

The authenticated staff ID is the history actor; never accept actor_id, role, ortenant_id from the request body.

reason is optional for normal forward transitions and required for cancellation.

Only ADMIN may request CANCELLED through this API.

Valid transitions, inventory release/consumption, and terminal-state rules come fromthe existing fulfilment service.

A successful response returns the updated order status, version, and transitiontimestamp.

10. Tenant Selection

For the first single-tenant deployment, resolve the active tenant as follows:

Authenticate the staff account.

Load its active memberships.

Require an active membership for the configured default tenant.

Construct an internal trusted StaffRequestContext containing staff_id,tenant_id, and role.

Do not accept a tenant ID from the LLM or request body. When multi-tenant staff accessis later exposed, use an explicit tenant-selection mechanism and verify the selected IDagainst current memberships on every request.

11. Service and Repository Contracts

11.1 Authentication service

async def authenticate(
    self,
    email: str,
    password: str,
) -> StaffAccount: ...

async def load_request_context(
    self,
    staff_id: UUID,
    tenant_id: UUID,
) -> StaffRequestContext: ...

Token encoding/decoding belongs to an application security adapter. Password hashingbelongs to a dedicated security adapter. Neither belongs in commerce domain models.

11.2 Staff order query service

async def list_orders(
    self,
    context: StaffRequestContext,
    filters: StaffOrderFilters,
    page: CursorPage,
) -> StaffOrderPage: ...

async def get_order(
    self,
    context: StaffRequestContext,
    order_id: UUID,
) -> StaffOrderDetails | None: ...

11.3 Fulfilment command service

Extend or call the existing service rather than creating parallel transition rules:

async def transition_order(
    self,
    tenant_id: UUID,
    order_id: UUID,
    expected_version: int,
    target_status: OrderStatus,
    actor: OrderActor,
    reason: str | None,
    idempotency: StaffIdempotencyRequest,
) -> OrderTransitionResult: ...

All order loads, locks, mutations, history inserts, inventory operations, idempotencylookups, and outbox inserts must be scoped by tenant_id.

12. Transaction and Concurrency Rules

For a new transition request, one PostgreSQL transaction must:

Claim or validate the staff idempotency key.

Lock the tenant-scoped order row.

Compare the current version with expected_version.

Validate role permission and the domain transition.

Apply the existing inventory release or consumption effect where required.

Update order status and increment version.

Append order_status_history with authenticated staff actor data.

Insert the notification outbox event required by specification 019.

Store the completed idempotent response.

Commit.

If any step fails, none of the effects may commit.

Concurrency behavior:

Version mismatch returns 409 stale_order_version with the current safe version andstatus so the client can refresh.

Reuse of the same idempotency key and identical canonical request returns the storedresponse.

Reuse of the same key with different input returns 409 idempotency_key_conflict.

Concurrent requests for the same key wait for or safely observe the winningtransaction; they must not execute the transition twice.

PostgreSQL deadlock/serialization retry behavior follows the bounded scoped retrypolicy already established for state-changing commerce transactions.

Retrying after an ambiguous HTTP disconnect is safe when the same idempotency key isreused.

13. Audit and History

Every successful new transition appends exactly one history row containing:

order_id
from_status
to_status
actor_type = STAFF
actor_id = authenticated staff ID
reason
created_at

Authentication audit events should record:

event type, staff ID when known, timestamp, safe request correlation ID,
tenant ID when resolved, outcome, and bounded failure category

Do not log access tokens, passwords, password hashes, full delivery addresses, or fullphone numbers. Application logs are not the authoritative order-status audit history.

14. Error Contract

Return a stable JSON error shape:

{
  "error": {
    "code": "invalid_transition",
    "message": "The requested order transition is not allowed.",
    "request_id": "safe-correlation-id"
  }
}

Required mappings:

HTTP

Code

Meaning

400

invalid_request

Invalid field, cursor, or status value

401

invalid_credentials

Login failed

401

invalid_access_token

Missing, expired, or invalid token

403

staff_access_denied

Valid identity lacks active permission

404

order_not_found

Missing or cross-tenant order

409

invalid_transition

Domain transition is not permitted

409

stale_order_version

Client used an old order version

409

idempotency_key_conflict

Key reused for different input

422

cancellation_reason_required

Admin cancellation lacks a reason

429

rate_limit_exceeded

Login or API limit exceeded

503

temporarily_unavailable

Safe transient failure after retries

Do not return stack traces, SQL messages, token-validation internals, password policyconfiguration, or cross-tenant resource details.

15. Configuration

Load secrets and environment-specific values through BaseSettings and .env forlocal development. Do not provide usable production defaults for secrets.

Required configuration categories:

STAFF_AUTH_ENABLED
STAFF_JWT_PRIVATE_KEY / secret-manager reference
STAFF_JWT_PUBLIC_KEY / secret-manager reference
STAFF_JWT_ALGORITHM
STAFF_JWT_ISSUER
STAFF_JWT_AUDIENCE
STAFF_ACCESS_TOKEN_TTL_SECONDS
STAFF_PASSWORD_MIN_LENGTH
STAFF_LOGIN_RATE_LIMIT
STAFF_API_RATE_LIMIT
STAFF_IDEMPOTENCY_RETENTION_HOURS

Rules:

Fail startup when staff APIs are enabled and required secure configuration is absent.

Never commit .env, signing private keys, bootstrap passwords, or generated tokens.

Production private keys belong in a secret manager or mounted secret, not sourcecontrol.

Key rotation must allow a controlled overlap where old unexpired tokens can beverified by key ID while new tokens use the new signing key.

16. Bootstrap Command

Provide an explicit operator-run command that creates the first staff account andtenant membership. It must:

accept email, display name, tenant ID, and role;

read the password without echoing it or accept it through a safe secret input;

validate the password policy;

hash it before persistence;

reject duplicate normalized email or duplicate membership safely;

never print the plaintext password or hash;

be idempotent only when the existing account/membership exactly matches the requestedsafe identity properties;

remain separate from FastAPI application startup.

No hard-coded default staff account or password is permitted.

17. Observability and Privacy

Expose low-cardinality metrics such as:

staff_login_attempts_total{outcome}
staff_api_requests_total{route_template,status_class}
staff_order_transitions_total{from_status,to_status,outcome}
staff_order_transition_duration_seconds
staff_authorization_denials_total{permission}

Rules:

Never label metrics with email, staff ID, order ID, phone, tenant name, address, JWTID, or idempotency key.

Structured logs may contain safe internal UUIDs only where operationally necessaryand access-controlled.

Mask phone numbers in list results; show complete delivery details only on anauthorized individual-order view.

Add Cache-Control: no-store to authenticated responses containing customer PII.

Ensure API documentation does not include live credentials or real customer examples.

18. Testing Requirements

18.1 Authentication

Correct credentials issue a valid short-lived token.

Unknown account, wrong password, and disabled account use indistinguishable loginerrors.

Missing, malformed, expired, wrong-audience, wrong-issuer, and invalid-signaturetokens are rejected.

Disabled account and inactive membership are rejected even with a previously issuedunexpired token.

Login rate limiting is enforced.

No credential or token appears in logs.

18.2 Authorization and tenant isolation

Both roles can list and view orders in their tenant.

Both roles can perform permitted forward transitions.

FULFILMENT_STAFF cannot cancel an order.

ADMIN can cancel only when the existing domain policy permits it.

Staff cannot read or mutate an order from another tenant.

Cross-tenant and nonexistent order lookups return the same response.

Supplying tenant, actor, or role values in request input cannot change trustedcontext.

18.3 Fulfilment behavior

Every allowed transition succeeds and increments the version once.

Skipped, reversed, and terminal-state transitions are rejected.

Delivery consumes inventory exactly once.

Eligible cancellation releases inventory exactly once.

Each successful new transition creates one correctly attributed history row.

Each notification-eligible transition creates one outbox event in the sametransaction.

A failed inventory/history/outbox write rolls back the entire operation.

18.4 Idempotency and concurrency

Exact replay with the same key returns the original response and produces no secondhistory, inventory, or notification effect.

Same key with different input is rejected.

Two staff members racing with the same version yield one success and one stale-versionresponse.

A client disconnect followed by a same-key retry returns the committed result.

Deadlock/serialization retries remain bounded and do not duplicate effects.

18.5 Query and privacy behavior

Filters and cursor pagination remain stable across equal timestamps.

Page-size and date-range limits are enforced.

List responses mask phone numbers and omit complete addresses.

Authorized detail responses contain only the delivery PII required for fulfilment.

Errors and metrics contain no secrets or customer PII.

19. Acceptance Criteria

This milestone is complete when:

An operator can bootstrap the first admin without a public registration endpoint.

Active staff can log in and receive a short-lived access token.

Every staff order endpoint rejects unauthenticated, disabled, unauthorized, andcross-tenant access.

Staff can list and inspect tenant orders using bounded cursor pagination.

Authorized staff can perform only transitions allowed by the existing domainservice.

Every new transition atomically updates the order, applies inventory effects,appends staff-attributed history, stores idempotency state, and inserts the requiredcustomer notification event.

Replays and concurrent stale updates cannot duplicate or overwrite fulfilmenteffects.

Customer Planner, Execute, and Response nodes remain unchanged.

Customer OTP remains outside the implementation.

Migrations, unit tests, repository integration tests, API tests, concurrency tests,and security-negative tests pass.

20. Recommended Implementation Order

Add staff account, membership, order version, and idempotency migrations.

Add staff identity, role, permission, and request-context contracts.

Implement password hashing, token signing/verification, and authentication service.

Add the secure first-admin bootstrap command.

Add authentication dependencies and login/current-identity routes.

Add tenant-scoped staff order query repository/service operations.

Extend the existing fulfilment command transaction with expected version,authenticated actor, idempotency, and notification outbox insertion.

Add list, detail, and transition routes.

Add rate limits, privacy controls, metrics, and structured audit events.

Complete unit, integration, API, rollback, replay, and concurrency tests.

21. Follow-up Milestones

After this specification:

Build a staff fulfilment dashboard against these APIs.

Add production deployment, secrets management, security headers, backup, restore,and disaster-recovery procedures.

Add a production payment-provider adapter when merchant credentials exist.

Add customer OTP and verified phone ownership only when product requirements justifythe additional onboarding friction.
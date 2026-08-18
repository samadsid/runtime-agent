# AI Commerce Agent

## Staff fulfilment API

When `STAFF_AUTH_ENABLED=true`, staff endpoints are exposed under `/api/staff/v1`.
Configure an asymmetric JWT private/public key pair, issuer, audience, active key
ID, and the existing `DEFAULT_TENANT_ID`; no signing key or usable production
secret has an application default. Previous public keys can be supplied through
`STAFF_JWT_PREVIOUS_PUBLIC_KEYS` during rotation.

After applying Alembic migrations, bootstrap the first account without starting
the API:

```bash
python -m app.staff.bootstrap \
  --email admin@example.com \
  --display-name "Operations Admin" \
  --tenant-id 00000000-0000-0000-0000-000000000001 \
  --role ADMIN
```

The command prompts without echo. Automation may pipe a secret and add
`--password-stdin`. Staff list/detail/status APIs derive the tenant and actor from
the current authenticated membership; callers never submit either value.

## Staff mobile application

The Android-first Expo application lives in `staff-mobile/`. It consumes only the
authenticated staff API and keeps protected order data in memory. Configure its public
API URL and environment using `staff-mobile/.env.example`; setup, tests, EAS preview APK,
and seeded-staging instructions are in `staff-mobile/README.md`.

## Database setup

Configure the `POSTGRES_*` environment variables, then apply application-owned
schema migrations before starting the API:

```bash
alembic upgrade head
```

Local development uses LangGraph's in-memory checkpointer by default. Set
`CHECKPOINTER_BACKEND=postgres` in production; startup will initialize and
migrate LangGraph's own checkpoint tables. `DEFAULT_TENANT_ID` remains the
server-owned customer-channel boundary and is also the only staff tenant selectable
in this first authenticated staff milestone.
`CUSTOMER_SUPPORT_PATH` is required and supplies the exact support contact or
path shown when an order is no longer eligible for self-service cancellation.

Saved delivery details use trusted channel identity and remain optional. For
local REST testing only, set `ALLOW_DEVELOPMENT_CUSTOMER_ID_HEADER=true` and
send `X-Dev-Customer-Id`; omit the header for guest checkout. The legacy
`X-Development-Customer-Id` spelling remains accepted temporarily. Both are
rejected while the setting is disabled and must not be enabled as a production
authentication mechanism.

## Customer web chat

The browser client lives in `frontend/`. Configure
`WEB_CHAT_ALLOWED_ORIGINS=["http://localhost:5173"]`, then run the API and:

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

The client sends an `X-Request-Id` UUID with each logical message and reuses it
for manual retry. Completed duplicate requests return their stored approved
reply; conflicting or ambiguous reuse is rejected safely. Apply migration
`011_customer_web_chat` before starting the updated API.

Checkout supports cash-on-delivery only. Delivery details remain in checkpointed
session state until explicit confirmation creates a durable order and closes the
source cart atomically. Confirmation also reserves authoritative inventory and
records initial status history in that transaction. Existing products are seeded
into `inventory_balances` from legacy `products.stock_quantity` by migration 006;
new products must be provisioned with a balance before they are sellable.

The fulfilment domain and persistence flow support preparing, dispatch, delivery,
and cancellation. No staff status HTTP endpoint is exposed until staff
authentication and order-management authorization are implemented.

Customers can list conversation-owned orders, inspect immutable order details,
and request cancellation. Cancellation requires a second, explicit confirmation
and is allowed only while the order remains `CONFIRMED`; the order, inventory
reservation, balance, and audit history change in one transaction.

Customers can also replace a persisted cart item's quantity and explicitly
confirm clearing a reviewed cart. Migration 007 adds monotonic cart versions so
stale or repeated clear confirmations cannot delete a newer cart state. Any
effective cart item mutation invalidates collected checkout state.

PostgreSQL integration tests require an already migrated, isolated database:

```bash
TEST_POSTGRES_DSN=postgresql://... pytest tests/test_postgres_cart_repository.py
```

## WhatsApp Providers

Apply all migrations, including `018_meta_whatsapp_cloud_api`, and select exactly
one transport with `WHATSAPP_PROVIDER=disabled|twilio|meta_cloud`. The REST/web
channels remain available in every mode. Switching provider while unresolved work
belongs to the old provider leaves WhatsApp workers not-ready until operators drain
or explicitly disposition those rows. Historical Twilio customer identifiers are
not rewritten or merged automatically; validate and explicitly migrate any mapping
that must be reused by Meta before cutover.

For Twilio, activate the Sandbox and send its displayed `join <sandbox-code>`
message from the test account. Start PostgreSQL and FastAPI, then expose FastAPI
through an HTTPS development tunnel.

Configure `WHATSAPP_PROVIDER=twilio`, `TWILIO_ACCOUNT_SID`,
`TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`, and the exact tunnel origin in
`TWILIO_WHATSAPP_PUBLIC_BASE_URL`. Keep credentials out of source control.
Configure the Sandbox inbound URL as
`{PUBLIC_BASE_URL}/webhooks/twilio/whatsapp` and its status callback as
`{PUBLIC_BASE_URL}/webhooks/twilio/whatsapp/status`, both using `POST`. Restart
after environment changes. When the tunnel changes, update both Twilio and the
environment because signatures use the configured URL rather than request host
or forwarded headers.

The Sandbox is test-only: users must join it, membership can expire, the shared
sender is externally rate-limited, and free-form replies are restricted to the
24-hour customer-service window. This milestone is text-only and does not
download media or use unapproved templates.

Customer order notification processing is intentionally opt-in. Leave
`CUSTOMER_NOTIFICATIONS_ENABLED=false` until approved Twilio Content Templates
exist; order transactions still retain durable notification intents while the
processor is disabled. To enable processing, set it to `true` and configure
`TWILIO_NOTIFICATION_CONTENT_SIDS` as a JSON object. It must contain an `HX...`
SID for each combination of `ORDER_CONFIRMED`, `ORDER_PREPARING`,
`ORDER_OUT_FOR_DELIVERY`, `ORDER_DELIVERED`, and `ORDER_CANCELLED` with
`en-IN`, `hi-IN`, and `hi-Latn-IN`, using keys such as
`"ORDER_CONFIRMED:en-IN"`. Startup deliberately fails if the enabled mapping is
incomplete, preventing notifications outside the service window from being
sent incorrectly.

For Meta Cloud API, configure `WHATSAPP_PROVIDER=meta_cloud`, the explicitly
versioned `META_GRAPH_API_VERSION` (currently `v25.0`), Phone Number ID, WABA ID,
access token, App Secret, high-entropy verification token, and HTTPS public base
URL. Configure both GET verification and POST events at
`{PUBLIC_BASE_URL}/webhooks/meta/whatsapp`, subscribe the WABA to `messages`, and
verify the intended test recipient before acceptance testing. Never commit or log
the access token, App Secret, verification token, signature, raw webhook, full
recipient, or message body.

Outside the customer-service window, Meta notifications require
`META_NOTIFICATION_TEMPLATES` as JSON keyed by order type and locale, for example
`"ORDER_CONFIRMED:en-IN":{"name":"order_confirmed_v1","language":"en_US"}`.
Every supported type/locale must map to a reviewed approved template before
notification processing is enabled. `hello_world` is setup-only. Confirm the pinned
Graph version in the Meta app before deployment and review it by 2027-11-18.

Operational endpoints are
`/health/live`, `/health/ready`, and `/metrics`.

Channel bodies are sensitive. The operating retention policy is to redact
bodies after 30 days and delete associated channel delivery records after 90
days through deployment-owned scheduled retention tooling.


Generate the RSA keys

From your repository root:

mkdir -p secrets

openssl genpkey \
  -algorithm RSA \
  -pkeyopt rsa_keygen_bits:3072 \
  -out secrets/staff-jwt-private.pem

openssl pkey \
  -in secrets/staff-jwt-private.pem \
  -pubout \
  -out secrets/staff-jwt-public.pem

chmod 600 secrets/staff-jwt-private.pem
chmod 644 secrets/staff-jwt-public.pem

Verify them:

openssl pkey \
  -in secrets/staff-jwt-private.pem \
  -check \
  -noout

openssl pkey \
  -pubin \
  -in secrets/staff-jwt-public.pem \
  -text \
  -noout

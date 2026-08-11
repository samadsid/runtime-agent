# AI Commerce Agent

## Database setup

Configure the `POSTGRES_*` environment variables, then apply application-owned
schema migrations before starting the API:

```bash
alembic upgrade head
```

Local development uses LangGraph's in-memory checkpointer by default. Set
`CHECKPOINTER_BACKEND=postgres` in production; startup will initialize and
migrate LangGraph's own checkpoint tables. `DEFAULT_TENANT_ID` supplies the
server-owned tenant boundary until authentication is implemented.
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

## Twilio WhatsApp Sandbox

Apply migration `010_twilio_whatsapp_channel`, activate the Twilio Sandbox for
WhatsApp, and send its displayed `join <sandbox-code>` message from the test
account. Start PostgreSQL and FastAPI, then expose FastAPI through an HTTPS
development tunnel.

Configure `TWILIO_WHATSAPP_ENABLED=true`, `TWILIO_ACCOUNT_SID`,
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
download media or use unapproved templates. Operational endpoints are
`/health/live`, `/health/ready`, and `/metrics`.

Channel bodies are sensitive. The operating retention policy is to redact
bodies after 30 days and delete associated channel delivery records after 90
days through deployment-owned scheduled retention tooling.

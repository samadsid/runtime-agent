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
send `X-Development-Customer-Id`; omit the header for guest checkout. The header
is rejected while the setting is disabled and must not be enabled as a
production authentication mechanism.

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

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

Checkout supports cash-on-delivery only. Delivery details remain in checkpointed
session state until explicit confirmation creates a durable order and closes the
source cart atomically.

PostgreSQL integration tests require an already migrated, isolated database:

```bash
TEST_POSTGRES_DSN=postgresql://... pytest tests/test_postgres_cart_repository.py
```

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.api.staff_routes import StaffAPIError, router
from commerce.models import (
    CatalogOptions,
    StaffAccount,
    StaffDashboardCounts,
    StaffDashboardSummary,
    StaffRequestContext,
    StaffRole,
    StaffStatus,
    StaffTenantMembership,
)
from infrastructure.security import InvalidAccessTokenError


class TokenCodec:
    expires_in = 900

    def encode(self, staff_id):
        return f"token:{staff_id}"

    def decode(self, token):
        if not token.startswith("token:"):
            raise InvalidAccessTokenError
        return UUID(token.removeprefix("token:"))


class Limiter:
    async def allow(self, key, limit, window_seconds=60):
        del key, limit, window_seconds
        return True


def application(role: StaffRole = StaffRole.ADMIN) -> tuple[FastAPI, StaffAccount]:
    now = datetime.now(timezone.utc)
    account = StaffAccount(
        id=uuid4(), email="staff@example.com", display_name="Staff",
        status=StaffStatus.ACTIVE, created_at=now, updated_at=now,
    )
    membership = StaffTenantMembership(
        staff_id=account.id, tenant_id=uuid4(), role=role,
        active=True, created_at=now, updated_at=now,
    )

    class Authentication:
        async def authenticate(self, email, password, request_id=None):
            del email, password, request_id
            return account

        async def load_request_context(self, staff_id, request_id):
            return StaffRequestContext(
                staff_id=staff_id, tenant_id=membership.tenant_id,
                role=membership.role, request_id=request_id,
            )

        async def memberships(self, staff_id):
            del staff_id
            return (membership,)

    class Repository:
        async def get_account(self, staff_id):
            return account if staff_id == account.id else None

    class Orders:
        async def dashboard_summary(self, context):
            assert context.tenant_id == membership.tenant_id
            return StaffDashboardSummary(
                counts=StaffDashboardCounts(
                    confirmed=3, preparing=2, out_for_delivery=1
                )
            )

    class Catalog:
        async def options(self, context):
            assert context.tenant_id == membership.tenant_id
            return CatalogOptions(categories=(), currencies=("INR",), units=("kg", "piece"))

    container = SimpleNamespace(
        settings=SimpleNamespace(
            STAFF_AUTH_ENABLED=True,
            STAFF_LOGIN_RATE_LIMIT=5,
            STAFF_API_RATE_LIMIT=120,
            APP_ENV="test",
        ),
        staff_token_codec=TokenCodec(),
        staff_rate_limiter=Limiter(),
        staff_authentication_service=Authentication(),
        staff_repository=Repository(),
        staff_order_query_service=Orders(),
        staff_catalog_service=Catalog(),
    )
    app = FastAPI()
    app.state.application_container = container
    app.include_router(router)

    @app.exception_handler(StaffAPIError)
    async def handle(_, error: StaffAPIError):
        return JSONResponse(
            status_code=error.status,
            content={"error": {"code": error.code, "message": error.message,
                               "request_id": error.request_id}},
            headers={"Cache-Control": "no-store"},
        )

    return app, account


@pytest.mark.asyncio
async def test_login_and_current_identity() -> None:
    app, account = application()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        login = await http.post(
            "/api/staff/v1/auth/login",
            json={"email": "staff@example.com", "password": "secret"},
        )
        assert login.status_code == 200
        assert login.json()["expires_in"] == 900
        me = await http.get(
            "/api/staff/v1/me",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        )
    assert me.status_code == 200
    assert me.json()["staff_id"] == str(account.id)
    assert me.json()["memberships"][0]["role"] == "ADMIN"


@pytest.mark.asyncio
async def test_missing_access_token_uses_stable_error() -> None:
    app, _ = application()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        response = await http.get("/api/staff/v1/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_access_token"
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_dashboard_summary_is_scoped_to_active_context() -> None:
    app, account = application()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        response = await http.get(
            "/api/staff/v1/dashboard/summary",
            headers={"Authorization": f"Bearer token:{account.id}"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "counts": {"confirmed": 3, "preparing": 2, "out_for_delivery": 1},
        "oldest_confirmed_orders": [],
    }


@pytest.mark.asyncio
async def test_admin_can_load_typed_catalog_options() -> None:
    app, account = application()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        response = await http.get(
            "/api/staff/v1/catalog/options",
            headers={"Authorization": f"Bearer token:{account.id}"},
        )
    assert response.status_code == 200
    assert response.json() == {
        "categories": [], "currencies": ["INR"], "units": ["kg", "piece"]
    }


@pytest.mark.asyncio
async def test_fulfilment_staff_cannot_access_catalog_options() -> None:
    app, account = application(StaffRole.FULFILMENT_STAFF)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        response = await http.get(
            "/api/staff/v1/catalog/options",
            headers={"Authorization": f"Bearer token:{account.id}"},
        )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "staff_access_denied"

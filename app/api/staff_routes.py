from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.staff_models import (
    CreateProductRequest,
    InventoryAdjustmentRequest,
    ProductStatusRequest,
    StaffLoginRequest,
    StaffLoginResponse,
    StaffMembershipResponse,
    StaffMeResponse,
    StaffTransitionRequest,
    StaffTransitionResponse,
    UpdateProductRequest,
)
from app.observability.staff_metrics import (
    STAFF_AUTHORIZATION_DENIALS,
    STAFF_LOGIN_ATTEMPTS,
)
from commerce.models import (
    AdminProductPage,
    CatalogOptions,
    InventoryAdjustmentResult,
    InventoryMovementPage,
    InventoryMovementType,
    InventorySummary,
    ManualInventoryMovementType,
    OrderStatus,
    ProductStatus,
    ProductWithInventory,
    StaffDashboardSummary,
    StaffOrderDetails,
    StaffOrderFilters,
    StaffOrderPage,
    StaffRequestContext,
    StaffRole,
    StockState,
)
from commerce.repositories import InvalidOrderTransitionError, OrderNotFoundError
from infrastructure.database.repositories.postgres_catalog_admin_repository import (
    CatalogAdminAccessDenied,
    CatalogAdminConflict,
    CatalogAdminInvalidCursor,
    CatalogAdminNotFound,
)
from infrastructure.security import InvalidAccessTokenError
from services.staff_auth import (
    InvalidStaffCredentialsError,
    StaffAccessDeniedError,
    normalize_staff_email,
)
from services.staff_catalog import CreateProductCommand, UpdateProductCommand
from services.staff_fulfilment import (
    IdempotencyKeyConflictError,
    StaffTransitionUnavailableError,
    StaleOrderVersionError,
)
from services.staff_orders import InvalidStaffOrderCursorError

router = APIRouter(prefix="/api/staff/v1", tags=["staff"])
bearer = HTTPBearer(auto_error=False)
IDEMPOTENCY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
IF_MATCH_PATTERN = re.compile(r'^"([1-9][0-9]*)"$')


def require_admin(context: StaffRequestContext) -> None:
    if context.role != StaffRole.ADMIN:
        STAFF_AUTHORIZATION_DENIALS.labels("catalog_inventory_admin").inc()
        raise StaffAPIError(403, "staff_access_denied", "Staff access is denied.", context.request_id)


def mutation_headers(context: StaffRequestContext, key: str | None, match: str | None, *, version_required: bool = True) -> tuple[str, int | None]:
    if key is None or not IDEMPOTENCY_PATTERN.fullmatch(key):
        raise StaffAPIError(400, "invalid_request", "A valid Idempotency-Key is required.", context.request_id)
    if not version_required:
        return key, None
    parsed = IF_MATCH_PATTERN.fullmatch(match or "")
    if parsed is None:
        raise StaffAPIError(400, "invalid_request", "A valid If-Match version is required.", context.request_id)
    return key, int(parsed.group(1))


def catalog_error(error: Exception, context: StaffRequestContext) -> StaffAPIError:
    if isinstance(error, CatalogAdminAccessDenied):
        return StaffAPIError(403, "staff_access_denied", "Staff access is denied.", context.request_id)
    if isinstance(error, CatalogAdminNotFound):
        return StaffAPIError(404, "product_not_found", "The product was not found.", context.request_id)
    if isinstance(error, CatalogAdminInvalidCursor):
        return StaffAPIError(400, "invalid_request", "The pagination cursor is invalid.", context.request_id)
    if isinstance(error, CatalogAdminConflict):
        status = 503 if error.code == "temporarily_unavailable" else 409
        message = error.code.replace("_", " ").capitalize() + "."
        if error.current is not None and error.code == "stale_product_version":
            message = f"The product changed; current version is {error.current.product.version}."
        elif error.current is not None and error.code == "stale_inventory_version":
            message = (
                f"Inventory changed; current version is {error.current.inventory_version}, "
                f"on hand is {error.current.on_hand_quantity}, reserved is "
                f"{error.current.reserved_quantity}."
            )
        return StaffAPIError(status, error.code, message, context.request_id)
    return StaffAPIError(400, "invalid_request", "The request is invalid.", context.request_id)


class StaffAPIError(Exception):
    def __init__(self, status: int, code: str, message: str, request_id: str) -> None:
        self.status = status
        self.code = code
        self.message = message
        self.request_id = request_id


def request_id(request: Request) -> str:
    supplied = request.headers.get("X-Request-Id", "").strip()
    return supplied[:128] if supplied else str(uuid4())


def require_enabled(request: Request):
    container = request.app.state.application_container
    if not container.settings.STAFF_AUTH_ENABLED:
        raise StaffAPIError(404, "not_found", "Not found.", request_id(request))
    return container


async def staff_context(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> StaffRequestContext:
    rid = request_id(request)
    container = require_enabled(request)
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise StaffAPIError(401, "invalid_access_token", "A valid access token is required.", rid)
    try:
        staff_id = container.staff_token_codec.decode(credentials.credentials)
        context = await container.staff_authentication_service.load_request_context(staff_id, rid)
    except InvalidAccessTokenError as error:
        raise StaffAPIError(401, "invalid_access_token", "A valid access token is required.", rid) from error
    except StaffAccessDeniedError as error:
        STAFF_AUTHORIZATION_DENIALS.labels("active_membership").inc()
        raise StaffAPIError(403, "staff_access_denied", "Staff access is denied.", rid) from error
    client = request.client.host if request.client else "unknown"
    if not await container.staff_rate_limiter.allow(
        f"api:{context.staff_id}:{client}", container.settings.STAFF_API_RATE_LIMIT
    ):
        raise StaffAPIError(429, "rate_limit_exceeded", "The request rate limit was exceeded.", rid)
    return context


@router.post("/auth/login", response_model=StaffLoginResponse)
async def login(body: StaffLoginRequest, request: Request) -> StaffLoginResponse:
    container = require_enabled(request)
    rid = request_id(request)
    if container.settings.APP_ENV == "production" and request.url.scheme != "https":
        raise StaffAPIError(400, "invalid_request", "HTTPS is required.", rid)
    client = request.client.host if request.client else "unknown"
    key = f"login:{normalize_staff_email(body.email)}:{client}"
    if not await container.staff_rate_limiter.allow(key, container.settings.STAFF_LOGIN_RATE_LIMIT):
        STAFF_LOGIN_ATTEMPTS.labels("rate_limited").inc()
        raise StaffAPIError(429, "rate_limit_exceeded", "The request rate limit was exceeded.", rid)
    try:
        account = await container.staff_authentication_service.authenticate(
            body.email, body.password, request_id=rid
        )
    except InvalidStaffCredentialsError as error:
        STAFF_LOGIN_ATTEMPTS.labels("invalid_credentials").inc()
        raise StaffAPIError(401, "invalid_credentials", "The email or password is invalid.", rid) from error
    STAFF_LOGIN_ATTEMPTS.labels("success").inc()
    return StaffLoginResponse(
        access_token=container.staff_token_codec.encode(account.id),
        expires_in=container.staff_token_codec.expires_in,
    )


@router.get("/me", response_model=StaffMeResponse)
async def me(request: Request, context: Annotated[StaffRequestContext, Depends(staff_context)]) -> StaffMeResponse:
    container = request.app.state.application_container
    account = await container.staff_repository.get_account(context.staff_id)
    if account is None:
        raise StaffAPIError(403, "staff_access_denied", "Staff access is denied.", context.request_id)
    memberships = await container.staff_authentication_service.memberships(context.staff_id)
    membership_responses = tuple(
        StaffMembershipResponse(tenant_id=item.tenant_id, role=item.role.value)
        for item in memberships
    )
    active_membership = StaffMembershipResponse(
        tenant_id=context.tenant_id, role=context.role.value
    )
    return StaffMeResponse(
        staff_id=account.id, display_name=account.display_name,
        active_membership=active_membership, memberships=membership_responses,
    )


@router.get("/catalog/options", response_model=CatalogOptions)
async def catalog_options(request: Request, context: Annotated[StaffRequestContext, Depends(staff_context)]):
    require_admin(context)
    return await request.app.state.application_container.staff_catalog_service.options(context)


@router.get("/catalog/products", response_model=AdminProductPage)
async def catalog_products(
    request: Request, context: Annotated[StaffRequestContext, Depends(staff_context)],
    status: ProductStatus | None = None, category_id: UUID | None = None,
    query: Annotated[str | None, Query(max_length=200)] = None,
    stock_state: StockState | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50, cursor: str | None = None,
):
    require_admin(context)
    try:
        return await request.app.state.application_container.staff_catalog_service.list_products(
            context, status=status, category_id=category_id,
            query=" ".join(query.casefold().split()) if query else None,
            stock_state=stock_state, limit=limit, cursor=cursor,
        )
    except Exception as error:
        raise catalog_error(error, context) from error


@router.post("/catalog/products", response_model=ProductWithInventory)
async def create_catalog_product(
    body: CreateProductRequest, request: Request,
    context: Annotated[StaffRequestContext, Depends(staff_context)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    require_admin(context)
    key, _ = mutation_headers(context, idempotency_key, None, version_required=False)
    try:
        return await request.app.state.application_container.staff_catalog_service.create_product(
            context, CreateProductCommand.model_validate(body.model_dump()), key
        )
    except Exception as error:
        raise catalog_error(error, context) from error


@router.get("/catalog/products/{product_id}", response_model=ProductWithInventory)
async def catalog_product(product_id: UUID, request: Request, context: Annotated[StaffRequestContext, Depends(staff_context)]):
    require_admin(context)
    result = await request.app.state.application_container.staff_catalog_service.get_product(context, product_id)
    if result is None:
        raise StaffAPIError(404, "product_not_found", "The product was not found.", context.request_id)
    return result


@router.patch("/catalog/products/{product_id}", response_model=ProductWithInventory)
async def update_catalog_product(
    product_id: UUID, body: UpdateProductRequest, request: Request,
    context: Annotated[StaffRequestContext, Depends(staff_context)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
):
    require_admin(context)
    if not body.model_fields_set:
        raise StaffAPIError(400, "invalid_request", "At least one field is required.", context.request_id)
    key, version = mutation_headers(context, idempotency_key, if_match)
    try:
        return await request.app.state.application_container.staff_catalog_service.update_product(
            context, product_id, version or 0,
            UpdateProductCommand.model_validate(body.model_dump()), key, body.model_fields_set,
        )
    except Exception as error:
        raise catalog_error(error, context) from error


@router.patch("/catalog/products/{product_id}/status", response_model=ProductWithInventory)
async def change_catalog_product_status(
    product_id: UUID, body: ProductStatusRequest, request: Request,
    context: Annotated[StaffRequestContext, Depends(staff_context)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
):
    require_admin(context)
    key, version = mutation_headers(context, idempotency_key, if_match)
    try:
        return await request.app.state.application_container.staff_catalog_service.change_status(
            context, product_id, version or 0, body.status, body.reason, key
        )
    except Exception as error:
        raise catalog_error(error, context) from error


@router.post("/inventory/products/{product_id}/adjustments", response_model=InventoryAdjustmentResult)
async def adjust_inventory(
    product_id: UUID, body: InventoryAdjustmentRequest, request: Request,
    context: Annotated[StaffRequestContext, Depends(staff_context)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
):
    require_admin(context)
    key, version = mutation_headers(context, idempotency_key, if_match)
    try:
        movement_type = ManualInventoryMovementType(body.movement_type)
    except ValueError as error:
        raise StaffAPIError(422, "invalid_movement_type", "The movement type is invalid.", context.request_id) from error
    try:
        return await request.app.state.application_container.staff_catalog_service.adjust(
            context, product_id, version or 0, movement_type, body.quantity, body.reason, key
        )
    except Exception as error:
        raise catalog_error(error, context) from error


@router.get("/inventory/products/{product_id}/movements", response_model=InventoryMovementPage)
async def inventory_movements(
    product_id: UUID, request: Request,
    context: Annotated[StaffRequestContext, Depends(staff_context)],
    movement_type: InventoryMovementType | None = None,
    created_from: datetime | None = None, created_to: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50, cursor: str | None = None,
):
    require_admin(context)
    if any(value is not None and value.utcoffset() is None for value in (created_from, created_to)) or (created_from and created_to and (created_from > created_to or created_to-created_from > timedelta(days=366))):
        raise StaffAPIError(400, "invalid_request", "The movement date range is invalid.", context.request_id)
    try:
        return await request.app.state.application_container.staff_catalog_service.movements(
            context, product_id, movement_type=movement_type, created_from=created_from,
            created_to=created_to, limit=limit, cursor=cursor,
        )
    except Exception as error:
        raise catalog_error(error, context) from error


@router.get("/inventory/summary", response_model=InventorySummary)
async def inventory_summary(request: Request, context: Annotated[StaffRequestContext, Depends(staff_context)]):
    require_admin(context)
    return await request.app.state.application_container.staff_catalog_service.summary(context)


@router.get("/orders", response_model=StaffOrderPage)
async def list_orders(
    request: Request,
    context: Annotated[StaffRequestContext, Depends(staff_context)],
    status: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    order_reference: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
):
    if status is not None:
        try:
            status = OrderStatus(status).value
        except ValueError as error:
            raise StaffAPIError(400, "invalid_request", "The order status is invalid.", context.request_id) from error
    supplied_dates = (created_from, created_to)
    if any(value is not None and value.utcoffset() is None for value in supplied_dates):
        raise StaffAPIError(
            400, "invalid_request", "Order dates must include a UTC offset.",
            context.request_id,
        )
    if created_from and created_to and (
        created_from > created_to or created_to - created_from > timedelta(days=31)
    ):
        raise StaffAPIError(400, "invalid_request", "The order date range is invalid.", context.request_id)
    try:
        page = await request.app.state.application_container.staff_order_query_service.list_orders(
            context, StaffOrderFilters(status=status, created_from=created_from,
                                       created_to=created_to, order_reference=order_reference),
            limit, cursor,
        )
    except InvalidStaffOrderCursorError as error:
        raise StaffAPIError(400, "invalid_request", "The pagination cursor is invalid.", context.request_id) from error
    return page


@router.get("/orders/{order_id}", response_model=StaffOrderDetails)
async def get_order(order_id: UUID, request: Request,
                    context: Annotated[StaffRequestContext, Depends(staff_context)]):
    details = await request.app.state.application_container.staff_order_query_service.get_order(context, order_id)
    if details is None:
        raise StaffAPIError(404, "order_not_found", "The order was not found.", context.request_id)
    return details


@router.get("/dashboard/summary", response_model=StaffDashboardSummary)
async def dashboard_summary(
    request: Request,
    context: Annotated[StaffRequestContext, Depends(staff_context)],
) -> StaffDashboardSummary:
    return await request.app.state.application_container.staff_order_query_service.dashboard_summary(
        context
    )


@router.patch("/orders/{order_id}/status", response_model=StaffTransitionResponse)
async def transition_order(
    order_id: UUID, body: StaffTransitionRequest, request: Request,
    context: Annotated[StaffRequestContext, Depends(staff_context)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> StaffTransitionResponse:
    if idempotency_key is None or not IDEMPOTENCY_PATTERN.fullmatch(idempotency_key):
        raise StaffAPIError(400, "invalid_request", "A valid Idempotency-Key is required.", context.request_id)
    match = IF_MATCH_PATTERN.fullmatch(if_match or "")
    if match is None:
        raise StaffAPIError(400, "invalid_request", "A valid If-Match version is required.", context.request_id)
    try:
        target = OrderStatus(body.target_status)
    except ValueError as error:
        raise StaffAPIError(400, "invalid_request", "The target status is invalid.", context.request_id) from error
    reason = body.reason or None
    if target == OrderStatus.CANCELLED and context.role != StaffRole.ADMIN:
        STAFF_AUTHORIZATION_DENIALS.labels("cancel_order").inc()
        raise StaffAPIError(403, "staff_access_denied", "Staff access is denied.", context.request_id)
    if target == OrderStatus.CANCELLED and not reason:
        raise StaffAPIError(422, "cancellation_reason_required", "A cancellation reason is required.", context.request_id)
    expected = int(match.group(1))
    canonical = json.dumps({"tenant_id": str(context.tenant_id), "staff_id": str(context.staff_id),
                            "operation": "transition_order", "order_id": str(order_id),
                            "expected_version": expected, "target_status": target.value,
                            "reason": reason}, sort_keys=True, separators=(",", ":"))
    try:
        result = await request.app.state.application_container.staff_fulfilment_service.transition_order(
            context=context, order_id=order_id, expected_version=expected,
            target_status=target, reason=reason, idempotency_key=idempotency_key,
            request_hash=sha256(canonical.encode()).hexdigest(),
        )
    except StaffAccessDeniedError as error:
        raise StaffAPIError(403, "staff_access_denied", "Staff access is denied.", context.request_id) from error
    except OrderNotFoundError as error:
        raise StaffAPIError(404, "order_not_found", "The order was not found.", context.request_id) from error
    except InvalidOrderTransitionError as error:
        raise StaffAPIError(409, "invalid_transition", "The requested order transition is not allowed.", context.request_id) from error
    except StaleOrderVersionError as error:
        message = f"The order changed; current version is {error.version} and status is {error.status.value}."
        raise StaffAPIError(409, "stale_order_version", message, context.request_id) from error
    except IdempotencyKeyConflictError as error:
        raise StaffAPIError(409, "idempotency_key_conflict", "The idempotency key was used for different input.", context.request_id) from error
    except StaffTransitionUnavailableError as error:
        raise StaffAPIError(503, "temporarily_unavailable", "The operation is temporarily unavailable.", context.request_id) from error
    return StaffTransitionResponse(order_id=result.order_id, status=result.status.value,
                                   version=result.version, transitioned_at=result.transitioned_at)

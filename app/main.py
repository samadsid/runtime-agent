from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.health import router as health_router
from app.api.meta_whatsapp_webhooks import router as meta_whatsapp_router
from app.api.routes import router
from app.api.staff_routes import StaffAPIError
from app.api.staff_routes import router as staff_router
from app.api.twilio_whatsapp_webhooks import router as twilio_router
from app.application_container import ApplicationContainer
from app.config.settings import settings
from app.observability.staff_metrics import STAFF_API_REQUESTS


@asynccontextmanager
async def lifespan(app: FastAPI):

    application_container = ApplicationContainer(settings=settings)
    await application_container.startup()

    app.state.application_container = application_container

    try:
        yield
    finally:
        await application_container.shutdown()


app = FastAPI(
    title="AI Commerce Agent",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.WEB_CHAT_ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "X-Dev-Customer-Id",
        "X-Development-Customer-Id",
        "X-Request-Id",
        "Authorization",
        "Idempotency-Key",
        "If-Match",
    ],
)


@app.exception_handler(StaffAPIError)
async def staff_api_error_handler(request: Request, error: StaffAPIError) -> JSONResponse:
    del request
    return JSONResponse(
        status_code=error.status,
        content={"error": {"code": error.code, "message": error.message,
                           "request_id": error.request_id}},
        headers={"Cache-Control": "no-store"},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, error: RequestValidationError) -> JSONResponse:
    if request.url.path.startswith("/api/staff/v1"):
        rid = request.headers.get("X-Request-Id") or "invalid-request"
        return JSONResponse(
            status_code=400,
            content={"error": {"code": "invalid_request",
                               "message": "The request is invalid.", "request_id": rid}},
            headers={"Cache-Control": "no-store"},
        )
    return JSONResponse(status_code=422, content={"detail": error.errors()})


@app.middleware("http")
async def staff_response_policy(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/staff/v1"):
        response.headers["Cache-Control"] = "no-store"
        route = request.scope.get("route")
        template = getattr(route, "path", "unmatched")
        STAFF_API_REQUESTS.labels(template, f"{response.status_code // 100}xx").inc()
    return response

app.include_router(router)
app.include_router(twilio_router)
app.include_router(meta_whatsapp_router)
app.include_router(health_router)
app.include_router(staff_router)

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.routes import router
from app.api.twilio_whatsapp_webhooks import router as twilio_router
from app.application_container import ApplicationContainer
from app.config.settings import settings


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
    allow_methods=["POST", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "X-Dev-Customer-Id",
        "X-Development-Customer-Id",
        "X-Request-Id",
    ],
)

app.include_router(router)
app.include_router(twilio_router)
app.include_router(health_router)

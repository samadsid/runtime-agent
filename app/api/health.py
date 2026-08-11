from __future__ import annotations

from datetime import datetime, timedelta, timezone

import asyncpg
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

router = APIRouter()


@router.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(request: Request) -> Response:
    container = request.app.state.application_container
    try:
        database = await container.channel_repository.ping()
    except (asyncpg.PostgresError, RuntimeError):
        database = False
    twilio = (
        not container.settings.TWILIO_WHATSAPP_ENABLED or container.twilio_configured
    )
    workers = True
    if (
        container.settings.TWILIO_WHATSAPP_ENABLED
        and container.settings.TWILIO_WHATSAPP_PROCESSOR_ENABLED
    ):
        threshold = timedelta(
            seconds=max(
                10.0, 3 * container.settings.TWILIO_WHATSAPP_PROCESSOR_INTERVAL_SECONDS
            )
        )
        now = datetime.now(timezone.utc)
        workers = all(
            worker is not None
            and worker.running
            and worker.last_success_at is not None
            and now - worker.last_success_at <= threshold
            for worker in (
                container.channel_inbound_processor,
                container.channel_outbound_dispatcher,
            )
        )
    healthy = database and twilio and workers
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={
            "status": "ready" if healthy else "not_ready",
            "components": {
                "database": database,
                "workers": workers,
                "twilio_config": twilio,
            },
        },
    )


@router.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

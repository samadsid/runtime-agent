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
    notification_worker = True
    if (
        container.settings.CUSTOMER_NOTIFICATIONS_ENABLED
        and container.settings.NOTIFICATION_PROCESSOR_ENABLED
    ):
        notification_workers = (
            (
                container.notification_outbox_processor,
                container.settings.NOTIFICATION_PROCESSOR_INTERVAL_SECONDS,
            ),
            (
                container.notification_reconciliation_job,
                container.settings.NOTIFICATION_RECONCILIATION_INTERVAL_SECONDS,
            ),
        )
        now = datetime.now(timezone.utc)
        notification_worker = all(
            worker is not None
            and worker.running
            and worker.last_success_at is not None
            and now - worker.last_success_at
            <= timedelta(seconds=max(10.0, 3 * interval))
            for worker, interval in notification_workers
        )
    healthy = database and twilio and workers and notification_worker
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={
            "status": "ready" if healthy else "not_ready",
            "components": {
                "database": database,
                "workers": workers,
                "twilio_config": twilio,
                "notification_worker": notification_worker,
            },
        },
    )


@router.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

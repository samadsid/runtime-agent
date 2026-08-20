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
    selected_provider = container.settings.WHATSAPP_PROVIDER
    whatsapp_config = selected_provider == "disabled" or (
        container.whatsapp_provider is not None
    )
    workers = True
    if (
        selected_provider != "disabled"
        and container.settings.WHATSAPP_PROCESSOR_ENABLED
    ):
        threshold = timedelta(
            seconds=max(
                10.0, 3 * container.settings.WHATSAPP_PROCESSOR_INTERVAL_SECONDS
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
    postgis = True
    if container.settings.DELIVERY_SERVICEABILITY_ENABLED:
        try:
            postgis = await container.delivery_zone_repository.postgis_available()
        except (asyncpg.PostgresError, RuntimeError):
            postgis = False
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
    workers = workers and not container.whatsapp_workers_blocked
    healthy = (
        database and whatsapp_config and workers and notification_worker and postgis
    )
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={
            "status": "ready" if healthy else "not_ready",
            "components": {
                "database": database,
                "workers": workers,
                "whatsapp_config": whatsapp_config,
                "whatsapp_provider": selected_provider,
                "notification_worker": notification_worker,
                "postgis": postgis,
            },
        },
    )


@router.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from commerce.models import ServiceabilityKind, ServiceabilityResult
from commerce.repositories.delivery_zone_repository import DeliveryZoneRepository


class DeliveryService:
    def __init__(
        self, repository: DeliveryZoneRepository, timeout_seconds: float
    ) -> None:
        self._repository = repository
        self._timeout = timeout_seconds

    async def check_serviceability(
        self, tenant_id: UUID, latitude: Decimal, longitude: Decimal
    ) -> ServiceabilityResult:
        checked_at = datetime.now(timezone.utc)
        try:
            zone = await asyncio.wait_for(
                self._repository.find_serviceable_zone(tenant_id, latitude, longitude),
                timeout=self._timeout,
            )
        except Exception:  # noqa: BLE001 -- every infrastructure failure fails closed.
            return ServiceabilityResult(
                kind=ServiceabilityKind.TEMPORARILY_UNAVAILABLE,
                checked_at=checked_at,
            )
        if zone is None:
            return ServiceabilityResult(
                kind=ServiceabilityKind.OUTSIDE_SERVICE_AREA,
                checked_at=checked_at,
            )
        return ServiceabilityResult(
            kind=ServiceabilityKind.SERVICEABLE,
            zone_id=zone.id,
            zone_name=zone.name,
            zone_version=zone.version,
            checked_at=checked_at,
        )

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from uuid import UUID

from commerce.models import DeliveryZone, DeliveryZoneStatus


class DeliveryZoneRepository(ABC):
    @abstractmethod
    async def find_serviceable_zone(
        self, tenant_id: UUID, latitude: Decimal, longitude: Decimal
    ) -> DeliveryZone | None: ...

    @abstractmethod
    async def list_zones(
        self,
        tenant_id: UUID,
        *,
        status: DeliveryZoneStatus | None,
        limit: int,
        cursor: UUID | None,
    ) -> tuple[DeliveryZone, ...]: ...

    @abstractmethod
    async def get_zone(self, tenant_id: UUID, zone_id: UUID) -> DeliveryZone | None: ...


class DeliveryZonePersistenceError(RuntimeError):
    pass


class DeliveryZoneNotFoundError(LookupError):
    pass


class DeliveryZoneConflictError(RuntimeError):
    def __init__(self, code: str, current: DeliveryZone | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.current = current


class InvalidDeliveryZoneGeometryError(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from commerce.models import InventoryBalance, InventoryReservation, OrderItem


class InventoryRepository(ABC):
    @abstractmethod
    async def reserve_for_order(
        self, order_id: UUID, items: tuple[OrderItem, ...]
    ) -> tuple[InventoryReservation, ...]: ...

    @abstractmethod
    async def release_for_order(
        self, order_id: UUID
    ) -> tuple[InventoryReservation, ...]: ...

    @abstractmethod
    async def consume_for_order(
        self, order_id: UUID
    ) -> tuple[InventoryReservation, ...]: ...

    @abstractmethod
    async def get_balance(self, product_id: UUID) -> InventoryBalance | None: ...


class InventoryStateConflictError(RuntimeError):
    pass

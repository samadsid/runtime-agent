from __future__ import annotations

from abc import ABC, abstractmethod
from types import TracebackType

from commerce.repositories.inventory_repository import InventoryRepository
from commerce.repositories.order_repository import OrderRepository


class FulfilmentUnitOfWork(ABC):
    orders: OrderRepository
    inventory: InventoryRepository

    @abstractmethod
    async def __aenter__(self) -> FulfilmentUnitOfWork: ...

    @abstractmethod
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    @abstractmethod
    async def commit(self) -> None: ...

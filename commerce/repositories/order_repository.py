from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from commerce.models import (
    ConfirmedOrderResult,
    FulfilmentActor,
    Order,
    OrderStatus,
    OrderStatusHistory,
    OrderSummary,
    StockShortage,
)


class OrderRepository(ABC):
    @abstractmethod
    async def create_confirmed_order_from_cart(
        self,
        tenant_id: UUID,
        conversation_id: UUID,
        cart_id: UUID,
        expected_cart_version: int,
        customer_name: str,
        phone_number: str,
        delivery_address: str,
    ) -> ConfirmedOrderResult: ...

    @abstractmethod
    async def list_for_conversation(
        self, conversation_id: UUID, limit: int
    ) -> tuple[OrderSummary, ...]: ...

    @abstractmethod
    async def get_for_conversation(
        self,
        conversation_id: UUID,
        order_id: UUID,
        *,
        for_update: bool = False,
    ) -> Order | None: ...

    @abstractmethod
    async def get_for_conversation_by_public_number(
        self, tenant_id: UUID, conversation_id: UUID, public_order_number: str
    ) -> Order | None: ...

    @abstractmethod
    async def get_latest_for_conversation(
        self, conversation_id: UUID
    ) -> Order | None: ...

    async def get_latest_order(self, conversation_id: UUID) -> Order | None:
        """Compatibility alias for the existing order-status capability."""
        return await self.get_latest_for_conversation(conversation_id)

    @abstractmethod
    async def get_by_id(
        self, order_id: UUID, *, for_update: bool = False
    ) -> Order | None: ...

    @abstractmethod
    async def transition_status(
        self,
        order_id: UUID,
        target_status: OrderStatus,
        actor: FulfilmentActor,
        reason: str | None = None,
    ) -> Order: ...

    @abstractmethod
    async def get_status_history(
        self, order_id: UUID
    ) -> tuple[OrderStatusHistory, ...]: ...


class CartNotAvailableForCheckoutError(ValueError):
    pass


class InsufficientStockError(ValueError):
    def __init__(self, shortages: tuple[StockShortage, ...]) -> None:
        super().__init__("One or more products have insufficient stock.")
        self.shortages = shortages


class OrderConfirmationPersistenceError(RuntimeError):
    pass


class OrderNotFoundError(LookupError):
    pass


class InvalidOrderTransitionError(ValueError):
    pass


class CustomerCancellationNotAllowedError(ValueError):
    def __init__(self, status: OrderStatus) -> None:
        super().__init__(
            f"Customer cancellation is not allowed from {status.value}."
        )
        self.status = status

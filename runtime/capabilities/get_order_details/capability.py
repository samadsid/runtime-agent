from __future__ import annotations

from decimal import Decimal

from commerce.models import CommerceSession
from commerce.services import CustomerOrderService
from runtime.capabilities import (
    Capability,
    CapabilityInput,
    CapabilityMetadata,
    CapabilityName,
    CapabilityOutput,
)
from runtime.capabilities.order_support import (
    format_amount,
    resolve_order_target,
    target_error_outcome,
)
from runtime.contracts import (
    ApprovedResponseFragment,
    ExecutionStatus,
    GeneratedExecutionOutcome,
    ResponseFragmentKind,
)


class GetOrderDetailsCapability(Capability[CommerceSession]):
    def __init__(self, service: CustomerOrderService) -> None:
        self._service = service

    @property
    def metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            name=CapabilityName.GET_ORDER_DETAILS,
            description="Returns customer-safe details for one owned order.",
        )

    async def execute(
        self, input: CapabilityInput[CommerceSession]
    ) -> CapabilityOutput[CommerceSession]:
        try:
            order = await resolve_order_target(
                input.data,
                input.session,
                self._service,
                input.context.conversation_id,
            )
        except (ValueError, LookupError) as error:
            return CapabilityOutput(
                session=input.session,
                outcome=target_error_outcome(error, input.session),
            )

        item_fragments = tuple(
            ApprovedResponseFragment(
                id=f"order-item-{index}",
                kind=ResponseFragmentKind.ITEM,
                text=(
                    f"{index}. {item.product_name} | "
                    f"Quantity {format_amount(item.quantity)} {item.unit} | "
                    f"Unit price {format_amount(item.unit_price)} | "
                    f"Amount {format_amount(item.unit_price * item.quantity)}"
                ),
            )
            for index, item in enumerate(order.items, start=1)
        )
        total = sum(
            (item.unit_price * item.quantity for item in order.items),
            start=Decimal(0),
        )
        timeline = tuple(
            ApprovedResponseFragment(
                id=f"order-status-{index}",
                text=f"{history.to_status.value} at {history.created_at.isoformat()}",
            )
            for index, history in enumerate(order.status_history, start=1)
        )
        fragments = (
            ApprovedResponseFragment(
                id="order-details",
                text=f"Order {order.id} | Status {order.status.value}",
            ),
            *item_fragments,
            ApprovedResponseFragment(
                id="order-total", text=f"Total {format_amount(total)}"
            ),
            ApprovedResponseFragment(
                id="order-payment",
                text=f"Payment method {order.payment_method.value}",
            ),
            ApprovedResponseFragment(
                id="order-delivery",
                text=(
                    f"Delivery to {order.customer_name} | "
                    f"Phone {order.phone_number} | Address {order.delivery_address}"
                ),
            ),
            ApprovedResponseFragment(
                id="order-created",
                text=(
                    f"Created {order.created_at.isoformat()} | "
                    f"Confirmed {order.confirmed_at.isoformat()}"
                ),
            ),
            *timeline,
        )
        protected = [
            str(order.id),
            order.status.value,
            format_amount(total),
            order.payment_method.value,
            order.customer_name,
            order.phone_number,
            order.delivery_address,
            order.created_at.isoformat(),
            order.confirmed_at.isoformat(),
        ]
        for item in order.items:
            protected.extend(
                (
                    item.product_name,
                    format_amount(item.quantity),
                    item.unit,
                    format_amount(item.unit_price),
                    format_amount(item.unit_price * item.quantity),
                )
            )
        for history in order.status_history:
            protected.extend((history.to_status.value, history.created_at.isoformat()))

        return CapabilityOutput(
            session=input.session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.SUCCESS,
                fragments=fragments,
                protected_values=tuple(protected),
            ),
        )

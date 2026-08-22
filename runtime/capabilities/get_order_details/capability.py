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
    customer_order_status,
    resolve_order_target,
    target_error_outcome,
)
from runtime.capabilities.checkout_support import mask_phone, payment_method_label
from runtime.contracts import (
    ApprovedResponseFragment,
    ExecutionStatus,
    GeneratedExecutionOutcome,
    ResponseFragmentKind,
    ResponseIcon,
    ResponseLayout,
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
                input.context.tenant_id,
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
                    f"{index}. {item.product_name}\n"
                    f"   {format_amount(item.quantity)} {item.unit} × "
                    f"{format_amount(item.unit_price)} = "
                    f"{format_amount(item.unit_price * item.quantity)}"
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
                text=f"{customer_order_status(history.to_status)} at {history.created_at.isoformat()}",
                kind=ResponseFragmentKind.BULLET,
            )
            for index, history in enumerate(order.status_history, start=1)
        )
        fragments = (
            ApprovedResponseFragment(
                id="order-details",
                text=f"Order {order.public_order_number}",
                kind=ResponseFragmentKind.SECTION,
            ),
            ApprovedResponseFragment(
                id="order-current-status",
                text=f"Status: {customer_order_status(order.status)}",
                kind=ResponseFragmentKind.FIELD,
            ),
            *item_fragments,
            ApprovedResponseFragment(
                id="order-total", text=f"Total: {format_amount(total)}",
                kind=ResponseFragmentKind.TOTAL,
            ),
            ApprovedResponseFragment(
                id="order-payment",
                text=f"Payment: {payment_method_label(order.payment_method)}",
                kind=ResponseFragmentKind.FIELD,
            ),
            ApprovedResponseFragment(
                id="order-delivery-heading",
                text="Delivery",
                kind=ResponseFragmentKind.SECTION,
            ),
            ApprovedResponseFragment(
                id="order-delivery",
                text=(
                    f"Name: {order.customer_name}\n"
                    f"Phone: {mask_phone(order.phone_number)}\n"
                    f"Address: {order.delivery_address}"
                ),
                kind=ResponseFragmentKind.FIELD,
            ),
            ApprovedResponseFragment(
                id="order-created",
                text=(
                    f"Created: {order.created_at.isoformat()}\n"
                    f"Confirmed: {order.confirmed_at.isoformat() if order.confirmed_at is not None else 'not yet'}"
                ),
                kind=ResponseFragmentKind.FIELD,
            ),
            ApprovedResponseFragment(
                id="order-status-history-heading",
                text="Status history",
                kind=ResponseFragmentKind.SECTION,
            ),
            *timeline,
        )
        protected = [
            order.public_order_number,
            customer_order_status(order.status),
            format_amount(total),
            payment_method_label(order.payment_method),
            order.customer_name,
            mask_phone(order.phone_number),
            order.delivery_address,
            order.created_at.isoformat(),
        ]
        if order.confirmed_at is not None:
            protected.append(order.confirmed_at.isoformat())
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
            protected.extend((customer_order_status(history.to_status), history.created_at.isoformat()))

        return CapabilityOutput(
            session=input.session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.SUCCESS,
                fragments=fragments,
                protected_values=tuple(protected),
                layout=ResponseLayout.SUMMARY,
                heading_emoji=ResponseIcon.ORDER,
            ),
        )

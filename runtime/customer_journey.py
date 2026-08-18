from __future__ import annotations

from datetime import datetime, timedelta, timezone

from commerce.models import (
    CommerceSession,
    DeferredCustomerIntent,
    DeferredCustomerIntentKind,
    DeferredOrderAction,
)
from runtime.capabilities.add_product_to_cart.capability import (
    AddProductToCartArguments,
)
from runtime.capabilities.browse_catalog.capability import BrowseCatalogArguments
from runtime.commands import ExecuteCapabilityCommand

_ORDER_ACTIONS = {
    "get_order_status": DeferredOrderAction.GET_STATUS,
    "list_orders": DeferredOrderAction.LIST,
    "get_order_details": DeferredOrderAction.VIEW_DETAILS,
    "cancel_order": DeferredOrderAction.CANCEL,
}


def defer_command(
    command: ExecuteCapabilityCommand, request_id: str | None
) -> DeferredCustomerIntent | None:
    """Convert only allowlisted, validated planner commands to bounded state."""
    if not request_id:
        return None
    now = datetime.now(timezone.utc)
    if command.capability == "browse_catalog":
        try:
            browse_args = BrowseCatalogArguments.model_validate(command.arguments)
        except ValueError:
            return None
        return DeferredCustomerIntent(
            kind=DeferredCustomerIntentKind.BROWSE_CATALOG,
            category_query=browse_args.category_query,
            source_request_id=request_id,
            created_at=now,
        )
    if command.capability == "search_product":
        query = command.arguments.get("query")
        if not isinstance(query, str) or not query.strip() or len(query.strip()) > 200:
            return None
        return DeferredCustomerIntent(
            kind=DeferredCustomerIntentKind.SEARCH_PRODUCT,
            product_query=query.strip(),
            source_request_id=request_id,
            created_at=now,
        )
    if command.capability == "add_product_to_cart":
        try:
            direct_args = AddProductToCartArguments.model_validate(command.arguments)
        except ValueError:
            return None
        return DeferredCustomerIntent(
            kind=DeferredCustomerIntentKind.DIRECT_CART_ADD,
            product_query=direct_args.product_query,
            quantity=direct_args.quantity,
            stated_unit=direct_args.stated_unit,
            source_request_id=request_id,
            created_at=now,
        )
    if command.capability == "view_cart":
        if command.arguments:
            return None
        return DeferredCustomerIntent(
            kind=DeferredCustomerIntentKind.VIEW_CART,
            source_request_id=request_id,
            created_at=now,
        )
    if command.capability in _ORDER_ACTIONS:
        allowed = {"order_reference", "ordinal", "latest", "limit", "confirmed"}
        if set(command.arguments) - allowed:
            return None
        reference = command.arguments.get("order_reference")
        ordinal = command.arguments.get("ordinal")
        latest = command.arguments.get("latest", False)
        limit = command.arguments.get("limit")
        confirmed = command.arguments.get("confirmed", False)
        if reference is not None and (
            not isinstance(reference, str)
            or not reference.strip()
            or len(reference.strip()) > 100
        ):
            return None
        if ordinal is not None and (
            not isinstance(ordinal, int) or isinstance(ordinal, bool) or ordinal < 1
        ):
            return None
        if not isinstance(latest, bool) or not isinstance(confirmed, bool):
            return None
        if limit is not None and (
            not isinstance(limit, int)
            or isinstance(limit, bool)
            or not 1 <= limit <= 10
        ):
            return None
        return DeferredCustomerIntent(
            kind=DeferredCustomerIntentKind.ORDER_MANAGEMENT,
            order_action=_ORDER_ACTIONS[command.capability],
            order_reference=reference.strip() if isinstance(reference, str) else None,
            order_ordinal=ordinal,
            order_latest=latest,
            order_limit=limit,
            order_confirmed=confirmed,
            source_request_id=request_id,
            created_at=now,
        )
    return None


def continuation_command(
    intent: DeferredCustomerIntent | None,
    *,
    ttl: timedelta = timedelta(minutes=15),
) -> ExecuteCapabilityCommand:
    if intent is None or datetime.now(timezone.utc) - intent.created_at > ttl:
        return ExecuteCapabilityCommand(
            capability="start_customer_shopping", arguments={}
        )
    if intent.kind is DeferredCustomerIntentKind.BROWSE_CATALOG:
        arguments: dict[str, object] = {"view": "categories"}
        if intent.category_query:
            arguments = {
                "view": "products",
                "category_query": intent.category_query,
            }
        return ExecuteCapabilityCommand(
            capability="browse_catalog", arguments=arguments
        )
    if intent.kind is DeferredCustomerIntentKind.SEARCH_PRODUCT:
        return ExecuteCapabilityCommand(
            capability="search_product", arguments={"query": intent.product_query}
        )
    if intent.kind is DeferredCustomerIntentKind.DIRECT_CART_ADD:
        arguments = {
            "product_query": intent.product_query,
            "quantity": intent.quantity,
        }
        if intent.stated_unit is not None:
            arguments["stated_unit"] = intent.stated_unit
        return ExecuteCapabilityCommand(
            capability="add_product_to_cart", arguments=arguments
        )
    if intent.kind is DeferredCustomerIntentKind.VIEW_CART:
        return ExecuteCapabilityCommand(capability="view_cart", arguments={})
    action = intent.order_action or DeferredOrderAction.GET_STATUS
    capability = {
        DeferredOrderAction.GET_STATUS: "get_order_status",
        DeferredOrderAction.LIST: "list_orders",
        DeferredOrderAction.VIEW_DETAILS: "get_order_details",
        DeferredOrderAction.CANCEL: "cancel_order",
    }[action]
    order_arguments: dict[str, object] = {}
    if intent.order_reference is not None:
        order_arguments["order_reference"] = intent.order_reference
    if intent.order_ordinal is not None:
        order_arguments["ordinal"] = intent.order_ordinal
    if intent.order_latest:
        order_arguments["latest"] = True
    if intent.order_limit is not None:
        order_arguments["limit"] = intent.order_limit
    if intent.order_confirmed:
        order_arguments["confirmed"] = True
    return ExecuteCapabilityCommand(capability=capability, arguments=order_arguments)


def with_deferred_intent(
    session: CommerceSession, intent: DeferredCustomerIntent | None
) -> CommerceSession:
    if intent is None:
        return session
    return session.model_copy(update={"deferred_customer_intent": intent})

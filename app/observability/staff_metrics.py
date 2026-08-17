from prometheus_client import Counter, Gauge, Histogram

STAFF_LOGIN_ATTEMPTS = Counter(
    "staff_login_attempts_total", "Staff login attempts", ("outcome",)
)
STAFF_API_REQUESTS = Counter(
    "staff_api_requests_total", "Staff API requests", ("route_template", "status_class")
)
STAFF_ORDER_TRANSITIONS = Counter(
    "staff_order_transitions_total", "Staff order transitions",
    ("from_status", "to_status", "outcome"),
)
STAFF_TRANSITION_DURATION = Histogram(
    "staff_order_transition_duration_seconds", "Staff transition duration"
)
STAFF_AUTHORIZATION_DENIALS = Counter(
    "staff_authorization_denials_total", "Staff authorization denials", ("permission",)
)
CATALOG_ADMIN_REQUESTS = Counter("catalog_admin_requests_total", "Catalog administration requests", ("operation", "outcome"))
INVENTORY_ADJUSTMENTS = Counter("inventory_adjustments_total", "Inventory adjustments", ("movement_type", "outcome"))
INVENTORY_ADJUSTMENT_DURATION = Histogram("inventory_adjustment_duration_seconds", "Inventory adjustment duration", ("movement_type",))
INVENTORY_LOW_STOCK_PRODUCTS = Gauge("inventory_low_stock_products", "Current low-stock product count")
INVENTORY_RECONCILIATION_FAILURES = Counter("inventory_reconciliation_failures_total", "Inventory reconciliation failures", ("category",))
CATALOG_CONCURRENCY_CONFLICTS = Counter("catalog_concurrency_conflicts_total", "Catalog concurrency conflicts", ("resource_type",))

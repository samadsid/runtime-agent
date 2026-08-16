from prometheus_client import Counter, Histogram

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

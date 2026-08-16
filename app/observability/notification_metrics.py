from prometheus_client import Counter, Gauge, Histogram

NOTIFICATION_EVENTS = Counter(
    "commerce_notifications_total",
    "Notification processing outcomes.",
    ("notification_type", "outcome"),
)
NOTIFICATION_LATENCY = Histogram(
    "commerce_notification_processing_seconds",
    "Notification outbox processing latency.",
    ("outcome",),
)
NOTIFICATION_LOCALE_FALLBACK = Counter(
    "commerce_notification_locale_fallback_total",
    "Notification template locale fallbacks.",
    ("channel",),
)
NOTIFICATION_WORKER_HEALTH = Gauge(
    "commerce_notification_worker_healthy",
    "Whether the notification worker's latest iteration succeeded.",
    ("worker",),
)

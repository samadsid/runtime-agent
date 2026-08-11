from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

WEBHOOKS = Counter(
    "commerce_channel_webhooks_total",
    "Conversational channel webhook outcomes.",
    ("channel", "kind", "outcome"),
)
INBOX_LATENCY = Histogram(
    "commerce_channel_inbox_processing_seconds",
    "Time spent processing an inbound message.",
    ("channel", "outcome"),
)
OUTBOUND = Counter(
    "commerce_channel_outbound_total",
    "Outbound message state outcomes.",
    ("channel", "outcome"),
)
RETRIES = Counter(
    "commerce_channel_retries_total",
    "Worker retry and dead-letter outcomes.",
    ("channel", "direction", "outcome"),
)
WORKER_HEALTH = Gauge(
    "commerce_channel_worker_healthy",
    "Whether the latest worker iteration succeeded.",
    ("channel", "worker"),
)

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
DELIVERY_EVENTS = Counter(
    "commerce_channel_delivery_events_total",
    "Normalized provider delivery status events.",
    ("channel", "status"),
)
AMBIGUOUS_SENDS = Counter(
    "commerce_channel_ambiguous_sends_total",
    "Outbound sends that may have been accepted by the provider.",
    ("channel",),
)
OUTBOUND_PRESENTATION = Counter(
    "commerce_channel_outbound_presentation_total",
    "WhatsApp outbound presentation mode and validation outcomes.",
    ("mode", "outcome"),
)

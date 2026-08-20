from prometheus_client import Counter, Histogram

WHATSAPP_INBOUND_MESSAGES = Counter(
    "whatsapp_inbound_messages_total",
    "Normalized WhatsApp inbound messages.",
    ("message_kind", "outcome"),
)
DELIVERY_SERVICEABILITY_CHECKS = Counter(
    "delivery_serviceability_checks_total",
    "Delivery serviceability checks.",
    ("source", "outcome"),
)
DELIVERY_SERVICEABILITY_DURATION = Histogram(
    "delivery_serviceability_duration_seconds",
    "Delivery serviceability latency.",
    ("source", "outcome"),
)
DELIVERY_ZONE_MUTATIONS = Counter(
    "delivery_zone_mutations_total",
    "Delivery-zone mutation outcomes.",
    ("operation", "outcome"),
)
DELIVERY_ZONE_GEOMETRY_REJECTIONS = Counter(
    "delivery_zone_geometry_rejections_total",
    "Rejected delivery-zone geometry.",
    ("reason",),
)
REVERSE_GEOCODER_REQUESTS = Counter(
    "reverse_geocoder_requests_total",
    "Reverse geocoder requests.",
    ("provider", "outcome"),
)
SAVED_LOCATION_REVALIDATIONS = Counter(
    "saved_location_revalidations_total",
    "Saved location revalidation outcomes.",
    ("outcome",),
)

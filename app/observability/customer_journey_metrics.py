from prometheus_client import Counter

CUSTOMER_JOURNEY_ENTRIES = Counter(
    "customer_journey_entries_total",
    "Customer journey entry outcomes.",
    ("customer_kind", "outcome"),
)
CUSTOMER_ONBOARDING_CONTINUATIONS = Counter(
    "customer_onboarding_continuations_total",
    "Post-onboarding continuation outcomes.",
    ("intent_kind", "outcome"),
)
CATALOG_CATEGORY_VIEWS = Counter(
    "catalog_category_views_total", "Catalog category view outcomes.", ("outcome",)
)
CATALOG_CATEGORY_SELECTIONS = Counter(
    "catalog_category_selections_total",
    "Catalog category selection outcomes.",
    ("outcome",),
)
CATALOG_PRODUCT_VIEWS = Counter(
    "catalog_product_views_total", "Catalog product view outcomes.", ("outcome",)
)
CATALOG_BROWSE_EXPIRED_REFERENCES = Counter(
    "catalog_browse_expired_references_total",
    "Expired catalog reference outcomes.",
    ("kind",),
)


class PrometheusCustomerJourneyObserver:
    def journey_entry(self, customer_kind: str, outcome: str) -> None:
        CUSTOMER_JOURNEY_ENTRIES.labels(customer_kind, outcome).inc()

    def onboarding_continuation(self, intent_kind: str, outcome: str) -> None:
        CUSTOMER_ONBOARDING_CONTINUATIONS.labels(intent_kind, outcome).inc()

    def category_view(self, outcome: str) -> None:
        CATALOG_CATEGORY_VIEWS.labels(outcome).inc()

    def category_selection(self, outcome: str) -> None:
        CATALOG_CATEGORY_SELECTIONS.labels(outcome).inc()

    def product_view(self, outcome: str) -> None:
        CATALOG_PRODUCT_VIEWS.labels(outcome).inc()

    def expired_reference(self, kind: str) -> None:
        CATALOG_BROWSE_EXPIRED_REFERENCES.labels(kind).inc()

from prometheus_client import Counter

RESPONSE_RENDERED = Counter(
    "commerce_response_rendered_total",
    "Customer response rendering outcomes.",
    ("layout", "mode"),
)
RESPONSE_NORMALIZATION = Counter(
    "commerce_response_normalization_total",
    "Whether deterministic response normalization changed the output.",
    ("applied",),
)
RESPONSE_VALIDATION_FAILURES = Counter(
    "commerce_response_validation_failures_total",
    "Low-cardinality response validation failures.",
    ("category",),
)


class PrometheusResponseObserver:
    def rendered(self, layout: str, mode: str) -> None:
        RESPONSE_RENDERED.labels(layout, mode).inc()

    def normalization(self, applied: bool) -> None:
        RESPONSE_NORMALIZATION.labels("true" if applied else "false").inc()

    def validation_failure(self, category: str) -> None:
        allowed = {
            "invalid_layout",
            "multiple_questions",
            "unapproved_question",
            "invalid_options",
            "invalid_option_order",
            "question_not_last",
            "provider_failure",
            "empty_message",
            "fenced_code",
            "markdown_heading",
            "html",
            "markdown_table",
            "unbalanced_bold",
            "unbalanced_italic",
        }
        RESPONSE_VALIDATION_FAILURES.labels(
            category if category in allowed else "grounding"
        ).inc()

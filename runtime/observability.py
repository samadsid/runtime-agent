from __future__ import annotations

from typing import Protocol


class CustomerJourneyObserver(Protocol):
    def journey_entry(self, customer_kind: str, outcome: str) -> None: ...
    def onboarding_continuation(self, intent_kind: str, outcome: str) -> None: ...
    def category_view(self, outcome: str) -> None: ...
    def category_selection(self, outcome: str) -> None: ...
    def product_view(self, outcome: str) -> None: ...
    def expired_reference(self, kind: str) -> None: ...
    def onboarding_event(self, event: str, outcome: str) -> None: ...


class NullCustomerJourneyObserver:
    def journey_entry(self, customer_kind: str, outcome: str) -> None:
        pass

    def onboarding_continuation(self, intent_kind: str, outcome: str) -> None:
        pass

    def category_view(self, outcome: str) -> None:
        pass

    def category_selection(self, outcome: str) -> None:
        pass

    def product_view(self, outcome: str) -> None:
        pass

    def expired_reference(self, kind: str) -> None:
        pass

    def onboarding_event(self, event: str, outcome: str) -> None:
        pass


class ResponseObserver(Protocol):
    def rendered(self, layout: str, mode: str) -> None: ...
    def normalization(self, applied: bool) -> None: ...
    def validation_failure(self, category: str) -> None: ...


class NullResponseObserver:
    def rendered(self, layout: str, mode: str) -> None:
        pass

    def normalization(self, applied: bool) -> None:
        pass

    def validation_failure(self, category: str) -> None:
        pass

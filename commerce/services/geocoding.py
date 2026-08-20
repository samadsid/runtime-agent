from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal

from commerce.models import ReverseGeocodeResult


class ReverseGeocoder(ABC):
    @abstractmethod
    async def reverse_geocode(
        self, latitude: Decimal, longitude: Decimal
    ) -> ReverseGeocodeResult: ...


class DisabledReverseGeocoder(ReverseGeocoder):
    async def reverse_geocode(
        self, latitude: Decimal, longitude: Decimal
    ) -> ReverseGeocodeResult:
        del latitude, longitude
        return ReverseGeocodeResult()


class ForwardGeocodeResult(ReverseGeocodeResult):
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    exact: bool = False


class ForwardGeocoder(ABC):
    @abstractmethod
    async def forward_geocode(self, address: str) -> ForwardGeocodeResult: ...


class DisabledForwardGeocoder(ForwardGeocoder):
    async def forward_geocode(self, address: str) -> ForwardGeocodeResult:
        del address
        return ForwardGeocodeResult()

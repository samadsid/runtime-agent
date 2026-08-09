from __future__ import annotations

from typing import Protocol


class PhoneValidationPolicy(Protocol):
    def is_valid(self, phone_number: str) -> bool: ...


class NonEmptyPhoneValidationPolicy:
    def is_valid(self, phone_number: str) -> bool:
        return bool(phone_number.strip())

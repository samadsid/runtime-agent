from __future__ import annotations


class CapabilityError(Exception):
    """Base exception for capability errors."""


class UnknownCapabilityError(CapabilityError):
    """Raised when a capability cannot be found."""


class DuplicateCapabilityError(CapabilityError):
    """Raised when duplicate capabilities are registered."""
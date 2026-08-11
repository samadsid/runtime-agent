from __future__ import annotations

from collections.abc import Mapping


class TwilioRequestValidator:
    def __init__(self, auth_token: str) -> None:
        from twilio.request_validator import RequestValidator

        self._validator = RequestValidator(auth_token)

    def validate(
        self, url: str, parameters: Mapping[str, str], signature: str | None
    ) -> bool:
        if not signature:
            return False
        return bool(self._validator.validate(url, dict(parameters), signature))

from __future__ import annotations

import hashlib
import hmac
import re

_SIGNATURE = re.compile(r"^sha256=([0-9a-fA-F]{64})$")


class MetaSignatureValidator:
    def __init__(self, app_secret: str) -> None:
        self._secret = app_secret.encode("utf-8")

    def validate(self, body: bytes, signature: str | None) -> bool:
        if signature is None or "," in signature:
            return False
        match = _SIGNATURE.fullmatch(signature.strip())
        if match is None:
            return False
        expected = hmac.new(self._secret, body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(match.group(1).lower(), expected)

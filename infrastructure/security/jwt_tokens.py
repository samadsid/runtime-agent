from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import jwt


class InvalidAccessTokenError(ValueError):
    pass


class AccessTokenCodec:
    def __init__(
        self,
        *,
        private_key: str,
        public_keys: dict[str, str],
        active_key_id: str,
        algorithm: str,
        issuer: str,
        audience: str,
        ttl_seconds: int,
    ) -> None:
        self._private_key = private_key
        self._public_keys = public_keys
        self._active_key_id = active_key_id
        self._algorithm = algorithm
        self._issuer = issuer
        self._audience = audience
        self._ttl_seconds = ttl_seconds

    @property
    def expires_in(self) -> int:
        return self._ttl_seconds

    def encode(self, staff_id: UUID, now: datetime | None = None) -> str:
        issued = now or datetime.now(timezone.utc)
        payload = {
            "iss": self._issuer,
            "aud": self._audience,
            "sub": str(staff_id),
            "jti": str(uuid4()),
            "iat": issued,
            "nbf": issued,
            "exp": issued + timedelta(seconds=self._ttl_seconds),
        }
        return jwt.encode(
            payload,
            self._private_key,
            algorithm=self._algorithm,
            headers={"kid": self._active_key_id},
        )

    def decode(self, token: str) -> UUID:
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") != self._algorithm:
                raise InvalidAccessTokenError("Unexpected signing algorithm.")
            key_id = header.get("kid")
            if not isinstance(key_id, str) or key_id not in self._public_keys:
                raise InvalidAccessTokenError("Unknown signing key.")
            payload = jwt.decode(
                token,
                self._public_keys[key_id],
                algorithms=[self._algorithm],
                issuer=self._issuer,
                audience=self._audience,
                options={
                    "require": ["iss", "aud", "sub", "jti", "iat", "nbf", "exp"]
                },
            )
            return UUID(payload["sub"])
        except (jwt.PyJWTError, KeyError, TypeError, ValueError) as error:
            if isinstance(error, InvalidAccessTokenError):
                raise
            raise InvalidAccessTokenError("Invalid access token.") from error

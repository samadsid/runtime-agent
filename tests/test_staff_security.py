from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from infrastructure.database.repositories.postgres_staff_order_repository import (
    mask_phone,
)
from infrastructure.security import (
    AccessTokenCodec,
    Argon2PasswordHasher,
    InvalidAccessTokenError,
)
from services.staff_auth import normalize_staff_email
from services.staff_orders import (
    InvalidStaffOrderCursorError,
    decode_cursor,
    encode_cursor,
)


def keys() -> tuple[str, str]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = private.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


def codec(*, audience: str = "staff") -> AccessTokenCodec:
    private, public = keys()
    return AccessTokenCodec(
        private_key=private,
        public_keys={"active": public},
        active_key_id="active",
        algorithm="RS256",
        issuer="commerce",
        audience=audience,
        ttl_seconds=900,
    )


def test_password_hashing_and_email_normalization() -> None:
    hasher = Argon2PasswordHasher()
    password_hash = hasher.hash("correct horse battery staple")

    assert password_hash.startswith("$argon2id$")
    assert hasher.verify(password_hash, "correct horse battery staple")
    assert not hasher.verify(password_hash, "wrong")
    assert normalize_staff_email("  STAFF@Example.COM ") == "staff@example.com"


def test_access_token_round_trip_and_expiry() -> None:
    token_codec = codec()
    staff_id = uuid4()
    now = datetime.now(timezone.utc)

    assert token_codec.decode(token_codec.encode(staff_id, now)) == staff_id

    expired = token_codec.encode(staff_id, now - timedelta(hours=1))
    with pytest.raises(InvalidAccessTokenError):
        token_codec.decode(expired)


def test_cursor_round_trip_and_phone_masking() -> None:
    created_at = datetime.now(timezone.utc)
    order_id = uuid4()

    assert decode_cursor(encode_cursor(created_at, order_id)) == (created_at, order_id)
    assert mask_phone("+919876543210") == "*********3210"
    with pytest.raises(InvalidStaffOrderCursorError):
        decode_cursor("not-a-cursor")

from __future__ import annotations

import logging
import unicodedata
from uuid import UUID

from commerce.models import StaffAccount, StaffRequestContext, StaffStatus
from infrastructure.database.repositories.postgres_staff_repository import (
    PostgresStaffRepository,
)
from infrastructure.security import AccessTokenCodec, Argon2PasswordHasher

logger = logging.getLogger(__name__)


class InvalidStaffCredentialsError(ValueError):
    pass


class StaffAccessDeniedError(PermissionError):
    pass


def normalize_staff_email(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


class StaffAuthenticationService:
    def __init__(self, repository: PostgresStaffRepository,
                 password_hasher: Argon2PasswordHasher,
                 token_codec: AccessTokenCodec, tenant_id: UUID) -> None:
        self._repository = repository
        self._password_hasher = password_hasher
        self._token_codec = token_codec
        self._tenant_id = tenant_id
        self._dummy_hash = password_hasher.hash("staff-authentication-dummy-secret")

    @property
    def token_codec(self) -> AccessTokenCodec:
        return self._token_codec

    async def authenticate(
        self, email: str, password: str, request_id: str | None = None
    ) -> StaffAccount:
        found = await self._repository.get_credentials(normalize_staff_email(email))
        password_hash = found[1] if found else self._dummy_hash
        verified = self._password_hasher.verify(password_hash, password)
        if found is None or not verified or found[0].status != StaffStatus.ACTIVE:
            category = (
                "disabled_account"
                if found is not None and found[0].status == StaffStatus.DISABLED
                else "invalid_credentials"
            )
            extra = {"event": "staff_login_failed", "failure_category": category}
            if request_id is not None:
                extra["request_id"] = request_id
            if found is not None:
                extra["staff_id"] = str(found[0].id)
            logger.warning("Staff login failed.", extra=extra)
            raise InvalidStaffCredentialsError("Invalid credentials.")
        logger.info(
            "Staff login succeeded.",
            extra={
                "event": "staff_login_succeeded",
                "staff_id": str(found[0].id),
                "request_id": request_id,
            },
        )
        return found[0]

    async def load_request_context(self, staff_id: UUID, request_id: str) -> StaffRequestContext:
        account = await self._repository.get_account(staff_id)
        membership = await self._repository.get_membership(staff_id, self._tenant_id)
        if account is None or account.status != StaffStatus.ACTIVE or membership is None or not membership.active:
            raise StaffAccessDeniedError("Staff access is not active.")
        return StaffRequestContext(staff_id=staff_id, tenant_id=self._tenant_id,
                                   role=membership.role, request_id=request_id)

    async def memberships(self, staff_id: UUID):
        return await self._repository.list_active_memberships(staff_id)

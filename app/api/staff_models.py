from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, StringConstraints

Password = Annotated[str, StringConstraints(min_length=1, max_length=1024)]


class StaffLoginRequest(BaseModel):
    email: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=320)]
    password: Password


class StaffLoginResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int


class StaffMembershipResponse(BaseModel):
    tenant_id: UUID
    role: str


class StaffMeResponse(BaseModel):
    staff_id: UUID
    display_name: str
    memberships: tuple[StaffMembershipResponse, ...]


class StaffTransitionRequest(BaseModel):
    target_status: str
    reason: Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=500)] = None


class StaffTransitionResponse(BaseModel):
    order_id: UUID
    status: str
    version: int
    transitioned_at: datetime


class StaffOrderListResponse(BaseModel):
    items: tuple[dict, ...]
    next_cursor: str | None

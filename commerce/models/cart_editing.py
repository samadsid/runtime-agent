from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PendingCartClear(BaseModel):
    model_config = ConfigDict(frozen=True)

    cart_id: UUID
    cart_version: int = Field(ge=0)
    requested_at: datetime

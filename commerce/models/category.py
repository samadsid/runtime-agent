from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class Category(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    tenant_id: UUID

    name: str
    description: str | None = None

    is_active: bool = True

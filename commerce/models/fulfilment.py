from __future__ import annotations

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class FulfilmentActorType(str, Enum):
    CUSTOMER = "CUSTOMER"
    STAFF = "STAFF"
    SYSTEM = "SYSTEM"


class FulfilmentActor(BaseModel):
    model_config = ConfigDict(frozen=True)

    actor_id: UUID | None = None
    actor_type: FulfilmentActorType


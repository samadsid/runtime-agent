from __future__ import annotations

from pydantic import BaseModel


class CapabilityMetadata(BaseModel):
    name: str

    description: str
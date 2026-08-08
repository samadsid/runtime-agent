from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ResponseLayout(str, Enum):
    PARAGRAPH = "paragraph"
    LIST = "list"


class ResponseComposition(BaseModel):
    model_config = ConfigDict(frozen=True)

    layout: ResponseLayout
    fragment_ids: tuple[str, ...]
    follow_up_id: str | None = None
    message: str = Field(min_length=1)

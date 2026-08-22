from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from runtime.contracts import ResponseLayout


class ResponseComposition(BaseModel):
    model_config = ConfigDict(frozen=True)

    layout: ResponseLayout
    fragment_ids: tuple[str, ...]
    follow_up_id: str | None = None
    message: str = Field(min_length=1)

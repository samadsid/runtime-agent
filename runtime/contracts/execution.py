from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExecutionStatus(str, Enum):
    SUCCESS = "success"
    MISSING_INPUT = "missing_input"
    INVALID_INPUT = "invalid_input"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    FAILURE = "failure"


class ResponseFragmentKind(str, Enum):
    TEXT = "text"
    ITEM = "item"


class ApprovedResponseFragment(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    kind: ResponseFragmentKind = ResponseFragmentKind.TEXT


class ApprovedOption(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    label: str = Field(min_length=1)


class FollowUpRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    options: tuple[ApprovedOption, ...] = ()

    @model_validator(mode="after")
    def validate_unique_option_ids(self) -> FollowUpRequest:
        ids = [option.id for option in self.options]
        if len(ids) != len(set(ids)):
            raise ValueError("Follow-up option IDs must be unique.")
        return self


class FixedExecutionOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    mode: Literal["fixed"] = "fixed"
    status: ExecutionStatus
    message: str = Field(min_length=1)


class GeneratedExecutionOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    mode: Literal["generated"] = "generated"
    status: ExecutionStatus
    fragments: tuple[ApprovedResponseFragment, ...] = ()
    follow_up: FollowUpRequest | None = None
    protected_values: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_presentation_data(self) -> GeneratedExecutionOutcome:
        if not self.fragments and self.follow_up is None:
            raise ValueError("A generated outcome requires approved response data.")

        fragment_ids = [fragment.id for fragment in self.fragments]
        if len(fragment_ids) != len(set(fragment_ids)):
            raise ValueError("Response fragment IDs must be unique.")

        statuses_requiring_follow_up = {
            ExecutionStatus.MISSING_INPUT,
            ExecutionStatus.INVALID_INPUT,
            ExecutionStatus.NOT_FOUND,
            ExecutionStatus.CONFLICT,
        }
        if self.status in statuses_requiring_follow_up and self.follow_up is None:
            raise ValueError(f"Status '{self.status.value}' requires a follow-up.")

        return self


ExecutionOutcome = Annotated[
    FixedExecutionOutcome | GeneratedExecutionOutcome,
    Field(discriminator="mode"),
]

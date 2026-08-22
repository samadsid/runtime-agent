from __future__ import annotations

import re
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
    SECTION = "section"
    ITEM = "item"
    BULLET = "bullet"
    FIELD = "field"
    TOTAL = "total"


class ResponseLayout(str, Enum):
    SHORT = "short"
    SELECTABLE_LIST = "selectable_list"
    INFORMATIONAL_LIST = "informational_list"
    SUMMARY = "summary"
    ERROR = "error"
    # Source compatibility for callers constructing the transient composition model.
    PARAGRAPH = "short"
    LIST = "selectable_list"


class ResponseIcon(str, Enum):
    CATALOG = "🛍️"
    SEARCH = "🔎"
    CART = "🛒"
    REVIEW = "📋"
    DELIVERY = "📍"
    PAYMENT = "💳"
    ORDER = "📦"
    SUCCESS = "✅"
    INFO = "ℹ️"
    WARNING = "⚠️"


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
    layout: ResponseLayout = ResponseLayout.SHORT
    heading_emoji: ResponseIcon | None = None


class GeneratedExecutionOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    mode: Literal["generated"] = "generated"
    status: ExecutionStatus
    fragments: tuple[ApprovedResponseFragment, ...] = ()
    follow_up: FollowUpRequest | None = None
    protected_values: tuple[str, ...] = ()
    layout: ResponseLayout | None = None
    heading_emoji: ResponseIcon | None = None

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

        if self.layout is None:
            kinds = {fragment.kind for fragment in self.fragments}
            items = tuple(
                fragment
                for fragment in self.fragments
                if fragment.kind is ResponseFragmentKind.ITEM
            )
            if self.follow_up is not None and self.follow_up.options:
                layout = ResponseLayout.SELECTABLE_LIST
            elif kinds & {
                ResponseFragmentKind.SECTION,
                ResponseFragmentKind.FIELD,
                ResponseFragmentKind.TOTAL,
            }:
                layout = ResponseLayout.SUMMARY
            elif items and all(
                re.match(r"^\s*\d+\.\s+", fragment.text) for fragment in items
            ):
                layout = ResponseLayout.SELECTABLE_LIST
            elif items or ResponseFragmentKind.BULLET in kinds:
                layout = ResponseLayout.INFORMATIONAL_LIST
            elif self.status is not ExecutionStatus.SUCCESS:
                layout = ResponseLayout.ERROR
            else:
                layout = ResponseLayout.SHORT
            object.__setattr__(self, "layout", layout)

        return self


ExecutionOutcome = Annotated[
    FixedExecutionOutcome | GeneratedExecutionOutcome,
    Field(discriminator="mode"),
]

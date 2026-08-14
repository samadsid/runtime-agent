from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CatalogBrowseKind(str, Enum):
    CATEGORIES = "CATEGORIES"
    PRODUCTS = "PRODUCTS"


class CatalogCategoryOption(BaseModel):
    model_config = ConfigDict(frozen=True)

    category_id: UUID
    name: str


class CatalogProductOption(BaseModel):
    model_config = ConfigDict(frozen=True)

    product_id: UUID
    name: str
    price: Decimal
    currency: str
    unit: str
    available: bool


class CatalogBrowseState(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: CatalogBrowseKind
    categories: tuple[CatalogCategoryOption, ...] = ()
    products: tuple[CatalogProductOption, ...] = ()
    category_id: UUID | None = None
    page: int = Field(ge=1)
    has_previous: bool
    has_next: bool
    created_at: datetime

    @model_validator(mode="after")
    def validate_projection(self) -> CatalogBrowseState:
        if self.kind is CatalogBrowseKind.CATEGORIES:
            if self.products or self.category_id is not None:
                raise ValueError("Category browse state cannot contain products.")
        elif self.categories:
            raise ValueError("Product browse state cannot contain categories.")
        return self


class CatalogCategoryPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: tuple[CatalogCategoryOption, ...]
    page: int = Field(ge=1)
    has_previous: bool
    has_next: bool


class CatalogProductPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: tuple[CatalogProductOption, ...]
    category_id: UUID | None = None
    page: int = Field(ge=1)
    has_previous: bool
    has_next: bool


class CategoryResolutionKind(str, Enum):
    ONE = "ONE"
    MULTIPLE = "MULTIPLE"
    NONE = "NONE"


class CategoryResolution(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: CategoryResolutionKind
    matches: tuple[CatalogCategoryOption, ...] = ()

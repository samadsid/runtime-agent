from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from commerce.models import CommerceSession
from commerce.services import CatalogBrowseService
from runtime.capabilities import (
    Capability,
    CapabilityInput,
    CapabilityMetadata,
    CapabilityOutput,
)
from runtime.capabilities.catalog_browse_support import (
    browse_result_output,
    temporary_failure,
)


class BrowseCatalogArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_query: str | None = Field(default=None, min_length=1, max_length=100)
    view: Literal["auto", "categories", "products"] = "auto"


class BrowseCatalogCapability(Capability[CommerceSession]):
    def __init__(
        self, service: CatalogBrowseService, clock: Callable[[], datetime] | None = None
    ) -> None:
        self._service = service
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @property
    def metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            name="browse_catalog",
            description="Browses authoritative catalog categories or products. Optional exact category_query and view auto/categories/products.",
        )

    async def execute(
        self, input: CapabilityInput[CommerceSession]
    ) -> CapabilityOutput[CommerceSession]:
        try:
            arguments = BrowseCatalogArguments.model_validate(input.data)
        except ValidationError:
            from runtime.capabilities.catalog_browse_support import _simple
            from runtime.contracts import ExecutionStatus

            return _simple(
                input.session,
                ExecutionStatus.INVALID_INPUT,
                "invalid-catalog-browse",
                "That catalog request is invalid.",
                "retry-catalog-browse",
                "What would you like to browse?",
            )
        query = arguments.category_query.strip() if arguments.category_query else None
        try:
            result = await self._service.browse(
                input.context.tenant_id, view=arguments.view, category_query=query
            )
        except Exception:  # noqa: BLE001 - repository failures are customer-safe here
            return temporary_failure(input.session)
        return browse_result_output(input.session, result, self._clock())

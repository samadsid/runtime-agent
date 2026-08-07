from __future__ import annotations

from commerce.models import CommerceSession
from commerce.services import SearchProductService
from runtime.capabilities import (
    Capability,
    CapabilityInput,
    CapabilityMetadata,
    CapabilityOutput,
)


class SearchProductCapability(Capability[CommerceSession]):
    def __init__(
        self,
        service: SearchProductService,
    ) -> None:

        self.service = service

    @property
    def metadata(
        self,
    ) -> CapabilityMetadata:

        return CapabilityMetadata(
            name="search_product",
            description=("Searches the product catalog using the customer's query."),
        )

    async def execute(
        self,
        input: CapabilityInput[CommerceSession],
    ) -> CapabilityOutput[CommerceSession]:

        query = str(input.data.get("query", "")).strip()

        if not query:
            return CapabilityOutput(
                success=False,
                session=input.session,
                message="No product query was provided.",
            )

        products = await self.service.search(query)

        session = input.session.model_copy(
            update={
                "recent_product_results": tuple(products),
                "selected_product": None,
            }
        )

        if not products:
            return CapabilityOutput(
                success=True,
                session=session,
                message=f"No products found for '{query}'.",
            )

        lines = [
            f"{product.name} - ₹{product.price}/{product.unit}" for product in products
        ]

        return CapabilityOutput(
            success=True,
            session=session,
            message="Available products:\n\n" + "\n".join(lines),
            data={
                "products": products,
            },
        )

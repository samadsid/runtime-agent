from __future__ import annotations

from decimal import Decimal
from hashlib import sha256
from typing import ClassVar
from uuid import UUID

from commerce.models import (
    DirectCartResult,
    DirectCartResultKind,
    PendingCartProductOption,
    Product,
)
from commerce.repositories import CartRepository, ProductRepository


class DirectCartServiceError(RuntimeError):
    pass


class UnitPolicy:
    _aliases: ClassVar[dict[str, str]] = {
        "kg": "kg",
        "kilogram": "kg",
        "kilograms": "kg",
        "kilo": "kg",
        "kilos": "kg",
        "g": "g",
        "gram": "g",
        "grams": "g",
        "pack": "pack",
        "packs": "pack",
        "packet": "pack",
        "packets": "pack",
        "piece": "piece",
        "pieces": "piece",
        "pc": "piece",
        "pcs": "piece",
    }

    def normalize(self, unit: str) -> str:
        normalized = " ".join(unit.casefold().split())
        return self._aliases.get(normalized, normalized)

    def equivalent(self, stated: str, canonical: str) -> bool:
        return self.normalize(stated) == self.normalize(canonical)


class ProductResolutionPolicy:
    @staticmethod
    def normalize(value: str) -> str:
        return " ".join(value.casefold().split())

    def resolve(self, query: str, candidates: list[Product]) -> Product | None:
        exact = [
            product
            for product in candidates
            if self.normalize(product.name) == self.normalize(query)
        ]
        if len(exact) == 1:
            return exact[0]
        if not exact and len(candidates) == 1:
            return candidates[0]
        return None


class DirectProductQueryPolicy:
    """Remove typed quantity/unit arguments if the planner repeats them in the query."""

    def __init__(self, unit_policy: UnitPolicy) -> None:
        self._units = unit_policy

    def catalog_query(
        self, product_query: str, quantity: Decimal, stated_unit: str | None
    ) -> str:
        canonical_unit = self._units.normalize(stated_unit) if stated_unit else None
        filtered: list[str] = []
        for token in product_query.split():
            cleaned = token.strip(".,;:!?()[]{}")
            if self._same_quantity(cleaned, quantity):
                continue
            if (
                canonical_unit is not None
                and self._units.normalize(cleaned) == canonical_unit
            ):
                continue
            filtered.append(token)
        candidate = " ".join(filtered).strip()
        return candidate or product_query.strip()

    @staticmethod
    def _same_quantity(token: str, quantity: Decimal) -> bool:
        try:
            return Decimal(token) == quantity
        except Exception:  # noqa: BLE001 - arbitrary product words are expected
            return False


class DirectCartService:
    def __init__(
        self,
        product_repository: ProductRepository,
        cart_repository: CartRepository,
        resolution_policy: ProductResolutionPolicy | None = None,
        unit_policy: UnitPolicy | None = None,
    ) -> None:
        self._products = product_repository
        self._carts = cart_repository
        self._resolution = resolution_policy or ProductResolutionPolicy()
        self._units = unit_policy or UnitPolicy()
        self._queries = DirectProductQueryPolicy(self._units)

    async def resolve_and_add(
        self,
        *,
        tenant_id: UUID,
        conversation_id: UUID,
        product_query: str,
        quantity: Decimal,
        stated_unit: str | None,
        request_id: str,
    ) -> DirectCartResult:
        catalog_query = self._queries.catalog_query(
            product_query, quantity, stated_unit
        )
        try:
            candidates = await self._products.search_candidates(
                tenant_id, catalog_query
            )
        except Exception as error:
            raise DirectCartServiceError("Catalog resolution failed.") from error
        if not candidates:
            return DirectCartResult(kind=DirectCartResultKind.NOT_FOUND)
        product = self._resolution.resolve(catalog_query, candidates)
        if product is None:
            return DirectCartResult(
                kind=DirectCartResultKind.AMBIGUOUS,
                options=tuple(
                    PendingCartProductOption(
                        product_id=item.id,
                        display_name=item.name,
                        canonical_unit=item.unit,
                    )
                    for item in candidates
                ),
            )
        try:
            return await self._add(
                tenant_id, conversation_id, product, quantity, stated_unit, request_id
            )
        except Exception as error:
            raise DirectCartServiceError("Direct cart mutation failed.") from error

    async def add_pending_selection(
        self,
        *,
        tenant_id: UUID,
        conversation_id: UUID,
        product_id: UUID,
        quantity: Decimal,
        stated_unit: str | None,
        request_id: str,
    ) -> DirectCartResult:
        try:
            product = await self._products.get_by_id(tenant_id, product_id)
        except Exception as error:
            raise DirectCartServiceError("Catalog reload failed.") from error
        if product is None:
            return DirectCartResult(kind=DirectCartResultKind.UNAVAILABLE)
        try:
            return await self._add(
                tenant_id, conversation_id, product, quantity, stated_unit, request_id
            )
        except Exception as error:
            raise DirectCartServiceError("Direct cart mutation failed.") from error

    async def _add(
        self,
        tenant_id: UUID,
        conversation_id: UUID,
        product: Product,
        quantity: Decimal,
        stated_unit: str | None,
        request_id: str,
    ) -> DirectCartResult:
        if not product.available:
            return DirectCartResult(
                kind=DirectCartResultKind.UNAVAILABLE, product=product
            )
        if stated_unit is not None and not self._units.equivalent(
            stated_unit, product.unit
        ):
            return DirectCartResult(
                kind=DirectCartResultKind.UNIT_MISMATCH,
                product=product,
                canonical_unit=product.unit,
            )
        fingerprint = sha256(
            f"{conversation_id}:{product.id}:{quantity}:{product.unit}".encode()
        ).hexdigest()
        return await self._carts.add_direct_item(
            tenant_id,
            conversation_id,
            product.id,
            quantity,
            product.unit,
            request_id,
            fingerprint,
        )

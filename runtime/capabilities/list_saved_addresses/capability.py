from __future__ import annotations

from commerce.models import CommerceSession, SavedAddressOption
from commerce.services import SavedDeliveryDetailsService
from runtime.capabilities import (
    Capability,
    CapabilityInput,
    CapabilityMetadata,
    CapabilityName,
    CapabilityOutput,
)
from runtime.capabilities.saved_delivery_support import guest_unavailable
from runtime.contracts import (
    ApprovedResponseFragment,
    ExecutionStatus,
    FollowUpRequest,
    GeneratedExecutionOutcome,
    ResponseFragmentKind,
)


class ListSavedAddressesCapability(Capability[CommerceSession]):
    def __init__(self, service: SavedDeliveryDetailsService) -> None:
        self._service = service

    @property
    def metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            name=CapabilityName.LIST_SAVED_ADDRESSES,
            description="Lists reusable delivery addresses for the trusted channel customer.",
        )

    async def execute(
        self, input: CapabilityInput[CommerceSession]
    ) -> CapabilityOutput[CommerceSession]:
        context = input.context
        if context.channel_customer_id is None:
            return guest_unavailable(input.session)
        profile, addresses = await self._service.list_addresses(
            context.tenant_id, context.channel, context.channel_customer_id
        )
        options = tuple(
            SavedAddressOption(
                address_id=address.id,
                label=address.label,
                delivery_address=address.delivery_address,
                is_default=address.is_default,
                version=address.version,
            )
            for address in addresses
        )
        session = input.session.model_copy(
            update={
                "recent_saved_addresses": options,
                "pending_saved_profile_use": None,
            }
        )
        if profile is None or not options:
            return CapabilityOutput(
                session=session,
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.NOT_FOUND,
                    fragments=(
                        ApprovedResponseFragment(
                            id="no-saved-addresses",
                            text="No saved delivery addresses were found.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="provide-delivery-address",
                        question="What delivery address should I use?",
                    ),
                ),
            )
        fragments = [
            ApprovedResponseFragment(
                id="saved-addresses", text="Saved delivery addresses:"
            )
        ]
        protected: list[str] = []
        for ordinal, option in enumerate(options, start=1):
            default = " (default)" if option.is_default else ""
            fragments.append(
                ApprovedResponseFragment(
                    id=f"saved-address-{ordinal}",
                    text=f"{ordinal}. {option.label}{default} — {option.delivery_address}",
                    kind=ResponseFragmentKind.ITEM,
                )
            )
            protected.extend((str(ordinal), option.label, option.delivery_address))
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.SUCCESS,
                fragments=tuple(fragments),
                follow_up=FollowUpRequest(
                    id="select-saved-address",
                    question="Which saved address would you like to use?",
                ),
                protected_values=tuple(protected),
            ),
        )

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from commerce.models import CommerceSession
from commerce.repositories import SavedDeliveryAddressNotFoundError
from commerce.services import SavedDeliveryDetailsService
from runtime.capabilities import (
    Capability,
    CapabilityInput,
    CapabilityMetadata,
    CapabilityName,
    CapabilityOutput,
)
from runtime.capabilities.saved_delivery_support import (
    invalid_saved_address_ordinal,
    resolve_option,
    stale_saved_address,
)
from runtime.contracts import (
    ApprovedResponseFragment,
    ExecutionStatus,
    GeneratedExecutionOutcome,
)


class SetDefaultAddressArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ordinal: int = Field(strict=True, ge=1)


class SetDefaultAddressCapability(Capability[CommerceSession]):
    def __init__(self, service: SavedDeliveryDetailsService) -> None:
        self._service = service

    @property
    def metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            name=CapabilityName.SET_DEFAULT_ADDRESS,
            description="Makes a recently listed saved address the profile default.",
        )

    async def execute(
        self, input: CapabilityInput[CommerceSession]
    ) -> CapabilityOutput[CommerceSession]:
        try:
            arguments = SetDefaultAddressArguments.model_validate(input.data)
        except ValidationError:
            return invalid_saved_address_ordinal(input.session)
        option = resolve_option(input.session, arguments.ordinal)
        if option is None:
            return invalid_saved_address_ordinal(input.session)
        context = input.context
        profile = await self._service.get_profile(
            context.tenant_id, context.channel, context.channel_customer_id
        )
        if profile is None:
            return stale_saved_address(input.session)
        try:
            updated = await self._service.set_default_address(
                context.tenant_id,
                context.channel_customer_id,
                profile.id,
                option.address_id,
            )
        except SavedDeliveryAddressNotFoundError:
            return stale_saved_address(input.session)
        return CapabilityOutput(
            session=input.session.model_copy(
                update={"recent_saved_addresses": (), "pending_saved_profile_use": None}
            ),
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.SUCCESS,
                fragments=(
                    ApprovedResponseFragment(
                        id="default-address-updated",
                        text=f"The saved address {updated.label} is now the default.",
                    ),
                ),
                protected_values=(updated.label,),
            ),
        )

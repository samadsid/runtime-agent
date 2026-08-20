from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, ValidationError

from commerce.models import CommerceSession, SavedAddressOption
from commerce.repositories import SavedDeliveryPersistenceError
from commerce.services import SavedDeliveryDetailsService
from runtime.capabilities import (
    Capability,
    CapabilityInput,
    CapabilityMetadata,
    CapabilityName,
    CapabilityOutput,
)
from runtime.capabilities.saved_delivery_support import (
    guest_unavailable,
    temporary_failure,
)
from runtime.contracts import (
    ApprovedResponseFragment,
    ExecutionStatus,
    FollowUpRequest,
    GeneratedExecutionOutcome,
    ResponseFragmentKind,
)


class SavedProfileField(str, Enum):
    ALL = "all"
    CUSTOMER_NAME = "customer_name"
    PHONE_NUMBER = "phone_number"
    DELIVERY_ADDRESS = "delivery_address"


class ViewSavedDeliveryProfileArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: SavedProfileField = SavedProfileField.ALL


class ViewSavedDeliveryProfileCapability(Capability[CommerceSession]):
    def __init__(self, service: SavedDeliveryDetailsService) -> None:
        self._service = service

    @property
    def metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            name=CapabilityName.VIEW_SAVED_DELIVERY_PROFILE,
            description=(
                "Shows the trusted customer's saved delivery profile. Use field "
                "customer_name, phone_number, delivery_address, or all."
            ),
        )

    async def execute(
        self, input: CapabilityInput[CommerceSession]
    ) -> CapabilityOutput[CommerceSession]:
        if input.context.channel_customer_id is None:
            return guest_unavailable(input.session)
        try:
            arguments = ViewSavedDeliveryProfileArguments.model_validate(input.data)
        except ValidationError:
            return self._invalid(input.session)
        try:
            profile, addresses = await self._service.list_addresses(
                input.context.tenant_id,
                input.context.channel,
                input.context.channel_customer_id,
            )
        except SavedDeliveryPersistenceError:
            return temporary_failure(input.session)

        options = tuple(
            SavedAddressOption(
                address_id=address.id,
                label=address.label,
                delivery_address=address.delivery_address,
                is_default=address.is_default,
                version=address.version,
                delivery_location=address.delivery_location,
                serviceability_status=address.serviceability_status,
            )
            for address in addresses
        )
        session = input.session.model_copy(update={"recent_saved_addresses": options})
        if profile is None:
            return self._not_found(session)

        fragments: list[ApprovedResponseFragment] = []
        protected: list[str] = []
        field = arguments.field
        if (
            field in {SavedProfileField.ALL, SavedProfileField.CUSTOMER_NAME}
            and profile.customer_name is not None
        ):
            fragments.append(
                ApprovedResponseFragment(
                    id="saved-customer-name",
                    text=f"Saved name: {profile.customer_name}",
                )
            )
            protected.append(profile.customer_name)
        if (
            field in {SavedProfileField.ALL, SavedProfileField.PHONE_NUMBER}
            and profile.phone_number is not None
        ):
            fragments.append(
                ApprovedResponseFragment(
                    id="saved-customer-phone",
                    text=f"Saved phone number: {profile.phone_number}",
                )
            )
            protected.append(profile.phone_number)
        if field in {SavedProfileField.ALL, SavedProfileField.DELIVERY_ADDRESS}:
            for ordinal, address in enumerate(options, start=1):
                default = " (default)" if address.is_default else ""
                fragments.append(
                    ApprovedResponseFragment(
                        id=f"saved-profile-address-{ordinal}",
                        text=f"{ordinal}. {address.label}{default} — {address.delivery_address}",
                        kind=ResponseFragmentKind.ITEM,
                    )
                )
                protected.extend(
                    (str(ordinal), address.label, address.delivery_address)
                )
        if not fragments:
            return self._field_not_found(session, field)
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.SUCCESS,
                fragments=tuple(fragments),
                protected_values=tuple(protected),
            ),
        )

    @staticmethod
    def _invalid(session: CommerceSession) -> CapabilityOutput[CommerceSession]:
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.INVALID_INPUT,
                fragments=(
                    ApprovedResponseFragment(
                        id="invalid-saved-profile-field",
                        text="That saved profile field is not supported.",
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="choose-saved-profile-field",
                    question="Would you like to see your saved name, phone number, address, or all delivery details?",
                ),
            ),
        )

    @staticmethod
    def _not_found(session: CommerceSession) -> CapabilityOutput[CommerceSession]:
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.NOT_FOUND,
                fragments=(
                    ApprovedResponseFragment(
                        id="no-saved-delivery-profile",
                        text="No saved delivery profile was found for this trusted channel customer.",
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="start-customer-onboarding",
                    question="Would you like to save delivery details for future orders?",
                ),
            ),
        )

    @staticmethod
    def _field_not_found(
        session: CommerceSession, field: SavedProfileField
    ) -> CapabilityOutput[CommerceSession]:
        labels = {
            SavedProfileField.CUSTOMER_NAME: "name",
            SavedProfileField.PHONE_NUMBER: "phone number",
            SavedProfileField.DELIVERY_ADDRESS: "address",
            SavedProfileField.ALL: "delivery details",
        }
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.NOT_FOUND,
                fragments=(
                    ApprovedResponseFragment(
                        id="saved-profile-field-not-found",
                        text=f"No saved {labels[field]} was found.",
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="update-saved-delivery-profile",
                    question="Would you like to add or update your saved delivery details?",
                ),
            ),
        )

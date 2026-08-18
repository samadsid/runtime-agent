from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from commerce.models import (
    ChannelName,
    CommerceSession,
    CustomerOnboardingState,
    OnboardingStage,
    SavedDeliveryProfile,
)
from commerce.services import NonEmptyPhoneValidationPolicy
from runtime.capabilities import CapabilityInput, ExecutionContext
from runtime.capabilities.collect_customer_onboarding_details import (
    CollectCustomerOnboardingDetailsCapability,
)
from runtime.capabilities.confirm_customer_onboarding import (
    ConfirmCustomerOnboardingCapability,
)
from runtime.capabilities.onboarding_support import missing_outcome
from runtime.capabilities.skip_customer_onboarding import (
    SkipCustomerOnboardingCapability,
)


def input_for(session: CommerceSession, data: dict[str, object] | None = None):
    return CapabilityInput[CommerceSession](
        session=session,
        data=data or {},
        context=ExecutionContext(
            tenant_id=uuid4(),
            conversation_id=uuid4(),
            channel=ChannelName.DEVELOPMENT_HTTP,
            channel_customer_id="customer-1",
            request_id="development-http:request-1",
        ),
    )


def test_first_onboarding_offer_welcomes_customer_to_meatuncle_first() -> None:
    outcome = missing_outcome(CustomerOnboardingState(), first_offer=True)

    assert [fragment.id for fragment in outcome.fragments] == [
        "customer-onboarding-welcome",
        "customer-onboarding-started",
    ]
    assert outcome.fragments[0].text == "Welcome to MeatUncle!"
    assert "saved for future orders" in outcome.fragments[1].text
    assert outcome.follow_up is not None
    assert outcome.follow_up.id == "request-customer-profile"


@pytest.mark.asyncio
async def test_partial_details_are_retained_and_requested_together() -> None:
    capability = CollectCustomerOnboardingDetailsCapability(
        NonEmptyPhoneValidationPolicy()
    )
    session = CommerceSession(
        customer_onboarding=CustomerOnboardingState(
            stage=OnboardingStage.COLLECTING_DETAILS
        )
    )

    result = await capability.execute(input_for(session, {"customer_name": "Samad"}))

    assert result.session.customer_onboarding.pending_customer_name == "Samad"
    assert (
        result.session.customer_onboarding.stage is OnboardingStage.COLLECTING_DETAILS
    )
    assert result.outcome.follow_up is not None
    assert "phone number" in result.outcome.follow_up.question
    assert "complete delivery address" in result.outcome.follow_up.question


@pytest.mark.asyncio
async def test_complete_details_enter_review_without_persistence() -> None:
    capability = CollectCustomerOnboardingDetailsCapability(
        NonEmptyPhoneValidationPolicy()
    )
    session = CommerceSession(
        customer_onboarding=CustomerOnboardingState(
            stage=OnboardingStage.COLLECTING_DETAILS
        )
    )

    result = await capability.execute(
        input_for(
            session,
            {
                "customer_name": "Samad",
                "phone_number": "9560717170",
                "delivery_address": "B-68, New Zafrabad, Delhi",
            },
        )
    )

    assert result.session.customer_onboarding.stage is OnboardingStage.REVIEWING_DETAILS
    assert result.outcome.follow_up is not None
    assert result.outcome.follow_up.id == "confirm-customer-profile"
    assert result.outcome.protected_values == (
        "Samad",
        "9560717170",
        "B-68, New Zafrabad, Delhi",
    )


class RecordingOnboardingService:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    async def complete_onboarding(self, *args: object) -> SavedDeliveryProfile:
        self.calls.append(args)
        return SavedDeliveryProfile(
            id=uuid4(),
            tenant_id=args[0] if isinstance(args[0], UUID) else UUID(int=0),
            channel=ChannelName.DEVELOPMENT_HTTP,
            channel_customer_id="customer-1",
            customer_name="Samad",
            phone_number="9560717170",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )


@pytest.mark.asyncio
async def test_confirmation_persists_reviewed_values_without_pii_arguments() -> None:
    service = RecordingOnboardingService()
    capability = ConfirmCustomerOnboardingCapability(service)  # type: ignore[arg-type]
    session = CommerceSession(
        customer_onboarding=CustomerOnboardingState(
            stage=OnboardingStage.REVIEWING_DETAILS,
            pending_customer_name="Samad",
            pending_phone_number="9560717170",
            pending_delivery_address="B-68, New Zafrabad, Delhi",
        )
    )

    result = await capability.execute(input_for(session))

    assert len(service.calls) == 1
    assert result.session.customer_onboarding == CustomerOnboardingState(
        stage=OnboardingStage.COMPLETED
    )
    assert result.outcome.fragments[0].id == "customer-profile-saved"


@pytest.mark.asyncio
async def test_skip_clears_pending_personal_data() -> None:
    session = CommerceSession(
        customer_onboarding=CustomerOnboardingState(
            stage=OnboardingStage.COLLECTING_DETAILS,
            pending_customer_name="Samad",
        )
    )

    result = await SkipCustomerOnboardingCapability().execute(input_for(session))

    assert result.session.customer_onboarding == CustomerOnboardingState(
        stage=OnboardingStage.SKIPPED
    )
    assert result.session.deferred_customer_intent is None

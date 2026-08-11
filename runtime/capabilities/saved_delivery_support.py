from __future__ import annotations

from commerce.models import CommerceSession, SavedAddressOption
from runtime.capabilities import CapabilityOutput
from runtime.contracts import (
    ApprovedResponseFragment,
    ExecutionStatus,
    FollowUpRequest,
    GeneratedExecutionOutcome,
)


def guest_unavailable(session: CommerceSession) -> CapabilityOutput[CommerceSession]:
    return CapabilityOutput(
        session=session.model_copy(
            update={
                "recent_saved_addresses": (),
                "pending_saved_profile_use": None,
                "pending_saved_details_save": None,
            }
        ),
        outcome=GeneratedExecutionOutcome(
            status=ExecutionStatus.NOT_FOUND,
            fragments=(
                ApprovedResponseFragment(
                    id="saved-addresses-unavailable-for-guest",
                    text=(
                        "Saved addresses are unavailable for this guest conversation; "
                        "one-time delivery details can still be used."
                    ),
                ),
            ),
            follow_up=FollowUpRequest(
                id="provide-delivery-address",
                question="What delivery address should I use for this checkout?",
            ),
        ),
    )


def invalid_saved_address_ordinal(
    session: CommerceSession,
) -> CapabilityOutput[CommerceSession]:
    return CapabilityOutput(
        session=session,
        outcome=GeneratedExecutionOutcome(
            status=ExecutionStatus.INVALID_INPUT,
            fragments=(
                ApprovedResponseFragment(
                    id="invalid-saved-address-ordinal",
                    text="That number does not identify a currently listed saved address.",
                ),
            ),
            follow_up=FollowUpRequest(
                id="review-saved-addresses",
                question="Would you like to list your saved addresses again?",
            ),
        ),
    )


def resolve_option(session: CommerceSession, ordinal: int) -> SavedAddressOption | None:
    index = ordinal - 1
    if index < 0 or index >= len(session.recent_saved_addresses):
        return None
    return session.recent_saved_addresses[index]


def stale_saved_address(session: CommerceSession) -> CapabilityOutput[CommerceSession]:
    return CapabilityOutput(
        session=session.model_copy(
            update={
                "recent_saved_addresses": (),
                "pending_saved_profile_use": None,
            }
        ),
        outcome=GeneratedExecutionOutcome(
            status=ExecutionStatus.CONFLICT,
            fragments=(
                ApprovedResponseFragment(
                    id="saved-address-changed",
                    text="The saved address changed or is no longer available.",
                ),
            ),
            follow_up=FollowUpRequest(
                id="review-saved-addresses",
                question="Would you like to review the current saved addresses?",
            ),
        ),
    )


def temporary_failure(session: CommerceSession) -> CapabilityOutput[CommerceSession]:
    return CapabilityOutput(
        session=session,
        outcome=GeneratedExecutionOutcome(
            status=ExecutionStatus.FAILURE,
            fragments=(
                ApprovedResponseFragment(
                    id="saved-delivery-details-temporary-failure",
                    text="Saved delivery details are temporarily unavailable. Please try again.",
                ),
            ),
        ),
    )

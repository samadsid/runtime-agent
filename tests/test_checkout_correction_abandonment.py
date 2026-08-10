from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from commerce.models import (
    CartItem,
    CheckoutStage,
    CheckoutState,
    CommerceSession,
    DeliveryDetailField,
    Product,
)
from commerce.services import CartService, NonEmptyPhoneValidationPolicy, OrderService
from runtime.capabilities import CapabilityInput, ExecutionContext
from runtime.capabilities.abandon_checkout import AbandonCheckoutCapability
from runtime.capabilities.confirm_order import ConfirmOrderCapability
from runtime.capabilities.update_delivery_details import (
    UpdateDeliveryDetailsCapability,
)
from runtime.contracts import ExecutionStatus
from runtime.prompts import PlannerPromptBuilder, PromptComposer, PromptLoader
from runtime.prompts.renderers import (
    CapabilityRenderer,
    CommerceSessionRenderer,
    ConversationRenderer,
)
from runtime.responses import ResponseGenerator, ResponseLayout
from tests.fakes import InMemoryCartRepository, InMemoryOrderRepository


def checkout_fixture() -> tuple[
    InMemoryCartRepository, CommerceSession, UpdateDeliveryDetailsCapability
]:
    product = Product(
        id=uuid4(),
        name="Chicken Breast",
        price=Decimal("320.00"),
        unit="kg",
    )
    repository = InMemoryCartRepository(
        items=(CartItem(product=product, quantity=Decimal(2)),)
    )
    cart = repository.carts[(UUID(int=0), UUID(int=0))]
    session = CommerceSession(
        cart_items=cart.items,
        checkout=CheckoutState(
            stage=CheckoutStage.READY_TO_CONFIRM,
            source_cart_id=cart.id,
            customer_name="Samad",
            phone_number="9876543210",
            delivery_address="Old Address",
        ),
    )
    capability = UpdateDeliveryDetailsCapability(
        CartService(repository), NonEmptyPhoneValidationPolicy()
    )
    return repository, session, capability


def capability_input(
    session: CommerceSession, data: dict[str, object] | None = None
) -> CapabilityInput[CommerceSession]:
    return CapabilityInput(
        session=session,
        data=data or {},
        context=ExecutionContext(tenant_id=UUID(int=0), conversation_id=UUID(int=0)),
    )


@pytest.mark.asyncio
async def test_named_correction_survives_turn_then_updates_pending_field() -> None:
    _, session, capability = checkout_fixture()

    requested = await capability.execute(
        capability_input(session, {"requested_field": "delivery_address"})
    )
    corrected = await capability.execute(
        capability_input(
            requested.session, {"delivery_address": "B-68 New Zafrabad Delhi"}
        )
    )

    assert (
        requested.session.checkout.pending_delivery_correction
        == DeliveryDetailField.DELIVERY_ADDRESS
    )
    assert requested.outcome.follow_up is not None
    assert requested.outcome.follow_up.id == "request-corrected-delivery-detail"
    assert corrected.session.checkout.pending_delivery_correction is None
    assert corrected.session.checkout.delivery_address == "B-68 New Zafrabad Delhi"
    assert corrected.session.checkout.stage == CheckoutStage.READY_TO_CONFIRM
    assert corrected.outcome.follow_up is not None
    assert corrected.outcome.follow_up.id == "confirm-corrected-order"
    assert any(
        "Chicken Breast" in fragment.text for fragment in corrected.outcome.fragments
    )


@pytest.mark.asyncio
async def test_multi_field_correction_is_atomic_and_preserves_other_values() -> None:
    _, session, capability = checkout_fixture()

    corrected = await capability.execute(
        capability_input(
            session,
            {"customer_name": "Aman", "delivery_address": "New Address"},
        )
    )
    rejected = await capability.execute(
        capability_input(
            corrected.session,
            {"customer_name": "Changed Again", "phone_number": "   "},
        )
    )

    assert corrected.session.checkout.customer_name == "Aman"
    assert corrected.session.checkout.phone_number == "9876543210"
    assert corrected.session.checkout.delivery_address == "New Address"
    assert rejected.outcome.status == ExecutionStatus.INVALID_INPUT
    assert rejected.session == corrected.session


@pytest.mark.asyncio
async def test_stale_source_cart_resets_checkout_and_refreshes_cart_snapshot() -> None:
    repository, session, capability = checkout_fixture()
    stale = session.model_copy(
        update={
            "checkout": session.checkout.model_copy(update={"source_cart_id": uuid4()})
        }
    )

    output = await capability.execute(
        capability_input(stale, {"delivery_address": "New Address"})
    )

    assert output.outcome.status == ExecutionStatus.NOT_FOUND
    assert output.session.checkout == CheckoutState()
    assert (
        output.session.cart_items == repository.carts[(UUID(int=0), UUID(int=0))].items
    )


@pytest.mark.asyncio
async def test_untrusted_identity_arguments_are_rejected_and_context_is_scoped() -> (
    None
):
    _, session, capability = checkout_fixture()

    supplied_id = await capability.execute(
        capability_input(session, {"source_cart_id": str(uuid4())})
    )
    scoped = await capability.execute(
        CapabilityInput(
            session=session,
            data={"delivery_address": "New Address"},
            context=ExecutionContext(tenant_id=uuid4(), conversation_id=uuid4()),
        )
    )

    assert supplied_id.outcome.status == ExecutionStatus.INVALID_INPUT
    assert supplied_id.session == session
    assert scoped.outcome.status == ExecutionStatus.NOT_FOUND
    assert scoped.session.cart_items == ()
    assert scoped.session.checkout == CheckoutState()


@pytest.mark.asyncio
async def test_abandonment_resets_only_checkout_and_is_idempotent() -> None:
    _, session, _ = checkout_fixture()
    capability = AbandonCheckoutCapability()

    abandoned = await capability.execute(capability_input(session))
    repeated = await capability.execute(capability_input(abandoned.session))

    assert abandoned.session.checkout == CheckoutState()
    assert abandoned.session.cart_items == session.cart_items
    assert abandoned.outcome.fragments[0].id == "checkout-abandoned"
    assert repeated.session == abandoned.session
    assert repeated.outcome.fragments[0].id == "checkout-not-active"


@pytest.mark.asyncio
async def test_correction_requires_new_confirmation_and_order_uses_new_address() -> (
    None
):
    cart_repository, session, correction = checkout_fixture()
    order_repository = InMemoryOrderRepository(cart_repository)

    corrected = await correction.execute(
        capability_input(session, {"delivery_address": "Corrected Address"})
    )
    assert order_repository.orders == []

    confirmed = await ConfirmOrderCapability(OrderService(order_repository)).execute(
        capability_input(corrected.session, {"confirmed": True})
    )

    assert confirmed.outcome.status == ExecutionStatus.SUCCESS
    assert len(order_repository.orders) == 1
    assert order_repository.orders[0].delivery_address == "Corrected Address"


def test_pending_correction_is_rendered_without_exposing_delivery_values() -> None:
    _, session, _ = checkout_fixture()
    session = session.model_copy(
        update={
            "checkout": session.checkout.model_copy(
                update={"pending_delivery_correction": DeliveryDetailField.PHONE_NUMBER}
            )
        }
    )

    rendered = CommerceSessionRenderer().render(session)

    assert "Pending delivery correction:\nphone_number" in rendered
    assert "9876543210" not in rendered
    assert "Old Address" not in rendered


def test_corrected_review_fallback_preserves_all_protected_values() -> None:
    _, session, _ = checkout_fixture()
    from runtime.capabilities.checkout_support import confirmation_review_outcome

    outcome = confirmation_review_outcome(
        session.checkout, session.cart_items, corrected=True
    )
    message = ResponseGenerator._render_approved_fallback(
        outcome,
        layout=ResponseLayout.LIST,
    )

    assert outcome.follow_up is not None
    assert outcome.follow_up.id == "confirm-corrected-order"
    assert all(value in message for value in outcome.protected_values)


def test_planner_contract_contains_correction_and_abandonment_boundaries() -> None:
    from runtime.capabilities import CapabilityRegistry

    _, _, correction = checkout_fixture()
    registry = CapabilityRegistry((correction, AbandonCheckoutCapability()))
    builder = PlannerPromptBuilder(
        loader=PromptLoader(),
        composer=PromptComposer(),
        conversation_renderer=ConversationRenderer(),
        commerce_session_renderer=CommerceSessionRenderer(),
        capability_renderer=CapabilityRenderer(),
        capability_registry=registry,
    )

    request = builder.build([], CommerceSession())
    system_prompt = request.messages[0].content

    assert "update_delivery_details" in system_prompt
    assert "abandon_checkout" in system_prompt
    assert '"Cancel checkout" is checkout abandonment' in system_prompt
    assert '"clear my cart" remains' in system_prompt

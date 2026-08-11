from decimal import Decimal
from uuid import UUID, uuid4

import asyncpg
import pytest
from pydantic import ValidationError

from commerce.models import (
    CartItem,
    CheckoutStage,
    CheckoutState,
    CommerceSession,
    Product,
    StockRecoveryAction,
    StockRecoveryOption,
    StockRecoveryState,
    StockShortage,
    StockUnavailable,
)
from commerce.repositories import OrderConfirmationPersistenceError
from commerce.services import CartService
from infrastructure.database.repositories import PostgresOrderRepository
from runtime.capabilities import CapabilityInput, CapabilityRegistry, ExecutionContext
from runtime.capabilities.accept_available_quantity import (
    AcceptAvailableQuantityCapability,
)
from runtime.capabilities.confirm_order import ConfirmOrderCapability
from runtime.capabilities.remove_from_cart import RemoveFromCartCapability
from runtime.capabilities.view_cart import ViewCartCapability
from runtime.commands import ExecuteCapabilityCommand, RespondCommand
from runtime.contracts import ExecutionStatus, Message
from runtime.planner import Planner
from runtime.planner.decision import DecisionType, PlannerDecision
from runtime.prompts import PlannerPromptBuilder, PromptComposer, PromptLoader
from runtime.prompts.renderers import (
    CapabilityRenderer,
    CommerceSessionRenderer,
    ConversationRenderer,
)
from tests.fakes import InMemoryCartRepository


def product() -> Product:
    return Product(
        id=uuid4(),
        name="Chicken Breast",
        price=Decimal(320),
        unit="kg",
    )


def capability_input(session: CommerceSession, data: dict[str, object]):
    return CapabilityInput[CommerceSession](
        session=session,
        data=data,
        context=ExecutionContext(
            tenant_id=UUID(int=0), conversation_id=UUID(int=0)
        ),
    )


def recovery_fixture(available: Decimal = Decimal(3)):
    chicken = product()
    repository = InMemoryCartRepository(
        items=(CartItem(product=chicken, quantity=Decimal(5)),)
    )
    repository.sellable_quantities[chicken.id] = available
    cart = repository.carts[(UUID(int=0), UUID(int=0))]
    shortage = StockShortage(
        product_id=chicken.id,
        product_name=chicken.name,
        unit=chicken.unit,
        requested_quantity=Decimal(5),
        available_quantity=Decimal(3),
    )
    recovery = StockRecoveryState(
        cart_id=cart.id,
        cart_version=cart.version,
        shortages=(shortage,),
        options=(
            StockRecoveryOption(
                ordinal=1,
                action=StockRecoveryAction.ACCEPT_AVAILABLE,
                shortage_ordinal=1,
            ),
        ),
    )
    session = CommerceSession(
        cart_items=cart.items,
        checkout=CheckoutState(
            stage=CheckoutStage.READY_TO_CONFIRM,
            source_cart_id=cart.id,
            source_cart_version=cart.version,
            customer_name="Samad",
            phone_number="9876543210",
            delivery_address="12 Market Road",
            stock_recovery=recovery,
        ),
    )
    return chicken, repository, cart, session


def test_stock_shortage_requires_a_real_decimal_shortage() -> None:
    chicken = product()

    with pytest.raises(ValidationError):
        StockShortage(
            product_id=chicken.id,
            product_name=chicken.name,
            unit=chicken.unit,
            requested_quantity=Decimal(3),
            available_quantity=Decimal(3),
        )


@pytest.mark.asyncio
async def test_stock_conflict_stores_exact_recovery_namespace() -> None:
    chicken, _, cart, session = recovery_fixture()

    class StockConflictService:
        async def create_confirmed_order_from_cart(self, **kwargs):
            return StockUnavailable(
                cart_id=cart.id,
                cart_version=cart.version,
                shortages=session.checkout.stock_recovery.shortages,
            )

    initial = session.model_copy(
        update={
            "checkout": session.checkout.model_copy(update={"stock_recovery": None})
        }
    )
    output = await ConfirmOrderCapability(StockConflictService()).execute(
        capability_input(initial, {"confirmed": True})
    )

    recovery = output.session.checkout.stock_recovery
    assert output.outcome.status == ExecutionStatus.CONFLICT
    assert recovery is not None
    assert tuple(option.action for option in recovery.options) == (
        StockRecoveryAction.ACCEPT_AVAILABLE,
        StockRecoveryAction.REMOVE_CART_ITEM,
        StockRecoveryAction.VIEW_CART,
        StockRecoveryAction.ABANDON_CHECKOUT,
    )
    assert recovery.options[0].shortage_ordinal == 1
    assert recovery.options[0].cart_ordinal is None
    assert recovery.options[1].cart_ordinal == 1
    assert chicken.name in output.outcome.fragments[1].text


@pytest.mark.asyncio
async def test_accept_available_caps_at_the_previously_offered_quantity() -> None:
    _, repository, cart, session = recovery_fixture(available=Decimal(4))
    capability = AcceptAvailableQuantityCapability(CartService(repository))

    output = await capability.execute(
        capability_input(session, {"shortage_ordinal": 1})
    )

    assert output.outcome.status == ExecutionStatus.SUCCESS
    assert output.session.cart_items[0].quantity == Decimal(3)
    assert output.session.checkout == CheckoutState()
    assert repository.carts[(UUID(int=0), UUID(int=0))].version == cart.version + 1


@pytest.mark.asyncio
async def test_accept_available_uses_lower_fresh_stock() -> None:
    _, repository, _, session = recovery_fixture(available=Decimal(2))
    capability = AcceptAvailableQuantityCapability(CartService(repository))

    output = await capability.execute(
        capability_input(session, {"shortage_ordinal": 1})
    )

    assert output.outcome.status == ExecutionStatus.SUCCESS
    assert output.session.cart_items[0].quantity == Decimal(2)


@pytest.mark.asyncio
async def test_zero_or_stale_recovery_never_mutates_the_cart() -> None:
    _, repository, cart, session = recovery_fixture(available=Decimal(0))
    capability = AcceptAvailableQuantityCapability(CartService(repository))

    zero = await capability.execute(
        capability_input(session, {"shortage_ordinal": 1})
    )
    assert zero.outcome.status == ExecutionStatus.CONFLICT
    assert zero.outcome.fragments[0].id == "stock-availability-changed"
    assert repository.carts[(UUID(int=0), UUID(int=0))] == cart

    repository.sellable_quantities[cart.items[0].product.id] = Decimal(2)
    repository.carts[(UUID(int=0), UUID(int=0))] = cart.model_copy(
        update={"version": cart.version + 1}
    )
    stale = await capability.execute(
        capability_input(session, {"shortage_ordinal": 1})
    )
    assert stale.outcome.status == ExecutionStatus.CONFLICT
    assert stale.session.checkout == CheckoutState()
    assert repository.carts[(UUID(int=0), UUID(int=0))].items[0].quantity == Decimal(
        5
    )


class RecoveryRoutingProvider:
    async def invoke(self, request, response_model):
        prompt = request.messages[-1].content
        accept_messages = (
            "accept the shown amount",
            "दिखाई गई मात्रा कर दो",
            "dikhaya hua amount kar do",
            "shown 3 kg kar do please",
        )
        if any(f"USER: {message}" in prompt for message in accept_messages):
            return PlannerDecision(
                type=DecisionType.EXECUTE_CAPABILITY,
                capability="accept_available_quantity",
                arguments={"shortage_ordinal": 1},
            )
        if "USER: remove that short item" in prompt:
            return PlannerDecision(
                type=DecisionType.EXECUTE_CAPABILITY,
                capability="remove_from_cart",
                arguments={"ordinal": 1},
            )
        if "USER: which one?" in prompt:
            return PlannerDecision(
                type=DecisionType.RESPOND,
                message="Which shortage number do you mean?",
            )
        raise AssertionError("Unexpected recovery routing scenario")


def recovery_planner(repository: InMemoryCartRepository) -> Planner:
    service = CartService(repository)
    registry = CapabilityRegistry[CommerceSession](
        (
            AcceptAvailableQuantityCapability(service),
            RemoveFromCartCapability(service),
            ViewCartCapability(service),
        )
    )
    return Planner(
        prompt_builder=PlannerPromptBuilder(
            loader=PromptLoader(),
            composer=PromptComposer(),
            conversation_renderer=ConversationRenderer(),
            commerce_session_renderer=CommerceSessionRenderer(),
            capability_renderer=CapabilityRenderer(),
            capability_registry=registry,
        ),
        llm_provider=RecoveryRoutingProvider(),  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    (
        "accept the shown amount",
        "दिखाई गई मात्रा कर दो",
        "dikhaya hua amount kar do",
        "shown 3 kg kar do please",
    ),
)
async def test_multilingual_recovery_routes_only_to_accept_available(
    message: str,
) -> None:
    _, repository, _, session = recovery_fixture()

    response = await recovery_planner(repository).plan([Message.user(message)], session)

    assert isinstance(response.command, ExecuteCapabilityCommand)
    assert response.command.capability == "accept_available_quantity"
    assert response.command.arguments == {"shortage_ordinal": 1}


@pytest.mark.asyncio
async def test_recovery_remove_uses_cart_ordinal_and_ambiguity_clarifies() -> None:
    _, repository, _, session = recovery_fixture()
    planner = recovery_planner(repository)

    remove = await planner.plan([Message.user("remove that short item")], session)
    ambiguous = await planner.plan([Message.user("which one?")], session)

    assert isinstance(remove.command, ExecuteCapabilityCommand)
    assert remove.command.capability == "remove_from_cart"
    assert remove.command.arguments == {"ordinal": 1}
    assert isinstance(ambiguous.command, RespondCommand)


@pytest.mark.asyncio
async def test_confirmation_retries_only_retryable_database_failures(
    monkeypatch,
) -> None:
    class Transaction:
        async def __aenter__(self):
            return None

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    class Connection:
        def __init__(self) -> None:
            self.attempts = 0

        def transaction(self):
            return Transaction()

        async def fetchval(self, *args):
            self.attempts += 1
            raise asyncpg.DeadlockDetectedError("deadlock")

    class Acquire:
        def __init__(self, connection) -> None:
            self.connection = connection

        async def __aenter__(self):
            return self.connection

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    connection = Connection()

    class Pool:
        def acquire(self):
            return Acquire(connection)

    class Adapter:
        pool = Pool()

    async def no_sleep(delay):
        return None

    monkeypatch.setattr("asyncio.sleep", no_sleep)
    repository = PostgresOrderRepository(Adapter())  # type: ignore[arg-type]

    with pytest.raises(OrderConfirmationPersistenceError):
        await repository.create_confirmed_order_from_cart(
            uuid4(),
            uuid4(),
            uuid4(),
            1,
            "Customer",
            "9876543210",
            "12 Market Road",
        )

    assert connection.attempts == 3

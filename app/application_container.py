from commerce.models import CommerceSession
from commerce.services import (
    CartService,
    CustomerOrderService,
    FulfilmentService,
    NonEmptyPhoneValidationPolicy,
    OrderService,
    SearchProductService,
)
from infrastructure.database import DatabasePool
from infrastructure.database.repositories import (
    PostgresCartRepository,
    PostgresFulfilmentUnitOfWork,
    PostgresInventoryRepository,
    PostgresOrderRepository,
    PostgresProductRepository,
)
from runtime.capabilities import CapabilityRegistry
from runtime.capabilities.add_to_cart import AddToCartCapability
from runtime.capabilities.cancel_order import CancelOrderCapability
from runtime.capabilities.checkout import CheckoutCapability
from runtime.capabilities.clear_cart import ClearCartCapability
from runtime.capabilities.collect_delivery_details import (
    CollectDeliveryDetailsCapability,
)
from runtime.capabilities.confirm_order import ConfirmOrderCapability
from runtime.capabilities.get_order_details import GetOrderDetailsCapability
from runtime.capabilities.get_order_status import GetOrderStatusCapability
from runtime.capabilities.greeting import GreetingCapability
from runtime.capabilities.list_orders import ListOrdersCapability
from runtime.capabilities.remove_from_cart import RemoveFromCartCapability
from runtime.capabilities.search_product import SearchProductCapability
from runtime.capabilities.select_product import SelectProductCapability
from runtime.capabilities.update_cart_item_quantity import (
    UpdateCartItemQuantityCapability,
)
from runtime.capabilities.view_cart import ViewCartCapability
from runtime.domain.commerce_runtime import CommerceRuntime
from runtime.graph import CommerceGraph
from runtime.graph.adapters import ConversationStateAdapter, LangChainMessageAdapter
from runtime.graph.memory import (
    GraphCheckpointer,
    MemoryManager,
)
from runtime.handlers import (
    CommandHandler,
    ExecuteCapabilityHandler,
    RespondHandler,
    WaitHandler,
)
from runtime.llm.gemini_provider import GeminiProvider
from runtime.planner import Planner
from runtime.prompts import (
    PlannerPromptBuilder,
    PromptComposer,
    PromptLoader,
    ResponsePromptBuilder,
)
from runtime.prompts.renderers import (
    CapabilityRenderer,
    CommerceSessionRenderer,
    ConversationRenderer,
)
from runtime.responses import ResponseGenerator

from .config.settings import Settings


class ApplicationContainer:
    def __init__(
        self,
        settings: Settings,
    ):

        self.settings = settings

        self._build_infrastructure()

        self._build_commerce()

        self._build_capabilities()

        self._build_prompting()

        self._build_handlers()

        self.graph_checkpointer = GraphCheckpointer(
            backend=self.settings.CHECKPOINTER_BACKEND,
            postgres_dsn=self.settings.database.dsn,
        )

    async def startup(self) -> None:
        """
        Start application infrastructure.
        """
        await self.database_pool.connect()
        try:
            await self.graph_checkpointer.start()
            self._build_runtime()
        except Exception:
            await self.graph_checkpointer.close()
            await self.database_pool.close()
            raise

    async def shutdown(self) -> None:
        """
        Shutdown application infrastructure.
        """
        await self.graph_checkpointer.close()
        await self.database_pool.close()

    def _build_infrastructure(self) -> None:
        """
        Construct infrastructure components.
        """

        self.database_pool = DatabasePool(
            config=self.settings.database,
        )

    def _build_commerce(self) -> None:
        """
        Construct commerce services and repositories.
        """

        self.product_repository = PostgresProductRepository(
            pool=self.database_pool,
        )

        self.cart_repository = PostgresCartRepository(
            pool=self.database_pool,
        )
        self.order_repository = PostgresOrderRepository(
            pool=self.database_pool,
        )
        self.inventory_repository = PostgresInventoryRepository(
            pool=self.database_pool,
        )

        self.search_product_service = SearchProductService(
            product_repository=self.product_repository,
        )

        self.cart_service = CartService(repository=self.cart_repository)
        self.order_service = OrderService(repository=self.order_repository)
        self.fulfilment_service = FulfilmentService(
            unit_of_work_factory=lambda: PostgresFulfilmentUnitOfWork(
                self.database_pool
            )
        )
        self.customer_order_service = CustomerOrderService(
            repository=self.order_repository,
            unit_of_work_factory=lambda: PostgresFulfilmentUnitOfWork(
                self.database_pool
            ),
        )
        self.phone_validation_policy = NonEmptyPhoneValidationPolicy()

    def _build_prompting(self) -> None:

        self.prompt_loader = PromptLoader()

        self.prompt_composer = PromptComposer()

        self.conversation_renderer = ConversationRenderer()

        self.commerce_session_renderer = CommerceSessionRenderer()

        self.capability_renderer = CapabilityRenderer()

        self.planner_prompt_builder = PlannerPromptBuilder(
            loader=self.prompt_loader,
            composer=self.prompt_composer,
            conversation_renderer=self.conversation_renderer,
            commerce_session_renderer=self.commerce_session_renderer,
            capability_renderer=self.capability_renderer,
            capability_registry=self.capability_registry,
        )

        self.response_prompt_builder = ResponsePromptBuilder(
            loader=self.prompt_loader,
            composer=self.prompt_composer,
        )

    def _build_capabilities(self) -> None:

        self.greeting_capability = GreetingCapability()

        self.search_product_capability = SearchProductCapability(
            service=self.search_product_service,
        )

        self.select_product_capability = SelectProductCapability()

        self.add_to_cart_capability = AddToCartCapability(
            service=self.cart_service,
        )

        self.view_cart_capability = ViewCartCapability(service=self.cart_service)

        self.remove_from_cart_capability = RemoveFromCartCapability(
            service=self.cart_service,
        )
        self.update_cart_item_quantity_capability = UpdateCartItemQuantityCapability(
            service=self.cart_service,
        )
        self.clear_cart_capability = ClearCartCapability(service=self.cart_service)
        self.checkout_capability = CheckoutCapability(service=self.cart_service)
        self.collect_delivery_details_capability = CollectDeliveryDetailsCapability(
            phone_policy=self.phone_validation_policy,
        )
        self.confirm_order_capability = ConfirmOrderCapability(
            service=self.order_service,
        )
        self.get_order_status_capability = GetOrderStatusCapability(
            service=self.order_service,
        )
        self.list_orders_capability = ListOrdersCapability(
            service=self.customer_order_service,
        )
        self.get_order_details_capability = GetOrderDetailsCapability(
            service=self.customer_order_service,
        )
        self.cancel_order_capability = CancelOrderCapability(
            service=self.customer_order_service,
            support_path=self.settings.CUSTOMER_SUPPORT_PATH,
        )

        self.capability_registry = CapabilityRegistry[CommerceSession](
            capabilities=[
                self.greeting_capability,
                self.search_product_capability,
                self.select_product_capability,
                self.add_to_cart_capability,
                self.view_cart_capability,
                self.remove_from_cart_capability,
                self.update_cart_item_quantity_capability,
                self.clear_cart_capability,
                self.checkout_capability,
                self.collect_delivery_details_capability,
                self.confirm_order_capability,
                self.get_order_status_capability,
                self.list_orders_capability,
                self.get_order_details_capability,
                self.cancel_order_capability,
            ]
        )

    def _build_handlers(self) -> None:

        self.respond_handler = RespondHandler[CommerceSession]()

        self.wait_handler = WaitHandler[CommerceSession]()

        self.execute_capability_handler = ExecuteCapabilityHandler[CommerceSession](
            registry=self.capability_registry,
        )

        self.command_handler = CommandHandler[CommerceSession](
            respond_handler=self.respond_handler,
            execute_capability_handler=self.execute_capability_handler,
            wait_handler=self.wait_handler,
        )

    def _build_runtime(self) -> None:

        self.message_adapter = LangChainMessageAdapter()

        self.graph_state_adapter = ConversationStateAdapter(
            self.message_adapter,
            tenant_id=self.settings.DEFAULT_TENANT_ID,
        )

        self.llm_provider = GeminiProvider()

        self.planner = Planner(
            prompt_builder=self.planner_prompt_builder,
            llm_provider=self.llm_provider,
        )

        self.response_generator = ResponseGenerator(
            prompt_builder=self.response_prompt_builder,
            llm_provider=self.llm_provider,
        )

        self.memory_manager = MemoryManager(
            checkpointer=self.graph_checkpointer,
        )

        self.commerce_graph = CommerceGraph(
            planner=self.planner,
            command_handler=self.command_handler,
            memory_manager=self.memory_manager,
            message_adapter=self.message_adapter,
            response_generator=self.response_generator,
        )

        self.runtime = CommerceRuntime(
            graph=self.commerce_graph,
            graph_state_adapter=self.graph_state_adapter,
        )

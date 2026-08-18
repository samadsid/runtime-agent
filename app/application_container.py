from datetime import timedelta

import httpx

from app.api.rate_limit import FixedWindowRateLimiter
from app.jobs import (
    ChannelInboundProcessor,
    ChannelOutboundDispatcher,
    InventoryReconciliationJob,
    NotificationOutboxProcessor,
    NotificationReconciliationJob,
    PaymentReconciliationJob,
)
from app.observability.customer_journey_metrics import (
    PrometheusCustomerJourneyObserver,
)
from channels.models import WhatsAppProviderName
from channels.templates import WhatsAppTemplateRegistry
from commerce.models import CommerceSession
from commerce.services import (
    CartService,
    CatalogBrowsePolicy,
    CatalogBrowseService,
    CustomerOrderService,
    DirectCartService,
    FulfilmentService,
    NonEmptyPhoneValidationPolicy,
    NotificationTemplateRegistry,
    OrderService,
    PaymentEventService,
    PaymentService,
    SavedDeliveryDetailsService,
    SearchProductService,
)
from infrastructure.channels.meta import (
    MetaSignatureValidator,
    MetaWebhookParser,
    MetaWhatsAppMessageProvider,
)
from infrastructure.channels.twilio import (
    TwilioRequestValidator,
    TwilioWhatsAppMessageProvider,
)
from infrastructure.database import DatabasePool
from infrastructure.database.repositories import (
    PostgresCartRepository,
    PostgresCatalogAdminRepository,
    PostgresChannelRepository,
    PostgresChatRequestRepository,
    PostgresFixedWindowRateLimiter,
    PostgresFulfilmentUnitOfWork,
    PostgresInventoryRepository,
    PostgresNotificationOutboxRepository,
    PostgresOrderRepository,
    PostgresPaymentRepository,
    PostgresProductRepository,
    PostgresSavedDeliveryDetailsRepository,
    PostgresStaffOrderRepository,
    PostgresStaffRepository,
)
from infrastructure.payments import FakePaymentProvider
from infrastructure.security import AccessTokenCodec, Argon2PasswordHasher
from runtime.capabilities import CapabilityRegistry
from runtime.capabilities.abandon_checkout import AbandonCheckoutCapability
from runtime.capabilities.accept_available_quantity import (
    AcceptAvailableQuantityCapability,
)
from runtime.capabilities.add_product_to_cart import AddProductToCartCapability
from runtime.capabilities.add_to_cart import AddToCartCapability
from runtime.capabilities.browse_catalog import BrowseCatalogCapability
from runtime.capabilities.cancel_order import CancelOrderCapability
from runtime.capabilities.checkout import CheckoutCapability
from runtime.capabilities.clear_cart import ClearCartCapability
from runtime.capabilities.collect_customer_onboarding_details import (
    CollectCustomerOnboardingDetailsCapability,
)
from runtime.capabilities.collect_delivery_details import (
    CollectDeliveryDetailsCapability,
)
from runtime.capabilities.confirm_customer_onboarding import (
    ConfirmCustomerOnboardingCapability,
)
from runtime.capabilities.confirm_order import ConfirmOrderCapability
from runtime.capabilities.confirm_save_delivery_details import (
    ConfirmSaveDeliveryDetailsCapability,
)
from runtime.capabilities.confirm_saved_profile_use import (
    ConfirmSavedProfileUseCapability,
)
from runtime.capabilities.delete_saved_address import DeleteSavedAddressCapability
from runtime.capabilities.get_order_details import GetOrderDetailsCapability
from runtime.capabilities.get_order_status import GetOrderStatusCapability
from runtime.capabilities.greeting import GreetingCapability
from runtime.capabilities.list_orders import ListOrdersCapability
from runtime.capabilities.list_saved_addresses import ListSavedAddressesCapability
from runtime.capabilities.remove_from_cart import RemoveFromCartCapability
from runtime.capabilities.resolve_catalog_browse import ResolveCatalogBrowseCapability
from runtime.capabilities.resolve_pending_cart_addition import (
    ResolvePendingCartAdditionCapability,
)
from runtime.capabilities.retry_online_payment import RetryOnlinePaymentCapability
from runtime.capabilities.save_delivery_details import SaveDeliveryDetailsCapability
from runtime.capabilities.search_product import SearchProductCapability
from runtime.capabilities.select_payment_method import SelectPaymentMethodCapability
from runtime.capabilities.select_product import SelectProductCapability
from runtime.capabilities.select_saved_address import SelectSavedAddressCapability
from runtime.capabilities.set_default_address import SetDefaultAddressCapability
from runtime.capabilities.skip_customer_onboarding import (
    SkipCustomerOnboardingCapability,
)
from runtime.capabilities.start_customer_onboarding import (
    StartCustomerOnboardingCapability,
)
from runtime.capabilities.start_customer_shopping import StartCustomerShoppingCapability
from runtime.capabilities.start_online_payment import StartOnlinePaymentCapability
from runtime.capabilities.switch_order_to_cash_on_delivery import (
    SwitchOrderToCashOnDeliveryCapability,
)
from runtime.capabilities.update_cart_item_quantity import (
    UpdateCartItemQuantityCapability,
)
from runtime.capabilities.update_delivery_details import (
    UpdateDeliveryDetailsCapability,
)
from runtime.capabilities.update_saved_address import UpdateSavedAddressCapability
from runtime.capabilities.view_cart import ViewCartCapability
from runtime.capabilities.view_payment_status import ViewPaymentStatusCapability
from runtime.capabilities.view_saved_delivery_profile import (
    ViewSavedDeliveryProfileCapability,
)
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
from services.staff_auth import StaffAuthenticationService
from services.staff_catalog import StaffCatalogService
from services.staff_fulfilment import StaffFulfilmentService
from services.staff_orders import StaffOrderQueryService

from .config.settings import Settings


class ApplicationContainer:
    def __init__(
        self,
        settings: Settings,
    ):

        self.settings = settings
        self.customer_journey_observer = PrometheusCustomerJourneyObserver()
        self.payment_rate_limiter = FixedWindowRateLimiter()
        self.twilio_request_validator = None
        self.twilio_message_provider = None
        self.channel_inbound_processor = None
        self.channel_outbound_dispatcher = None
        self.notification_outbox_processor = None
        self.notification_reconciliation_job = None
        self.twilio_configured = False
        self.meta_signature_validator = None
        self.meta_webhook_parser = None
        self.meta_message_provider = None
        self.meta_http_client: httpx.AsyncClient | None = None
        self.whatsapp_provider = None
        self.whatsapp_provider_name: WhatsAppProviderName | None = None
        self.whatsapp_sender_id: str | None = None
        self.whatsapp_workers_blocked = False
        self.staff_token_codec: AccessTokenCodec | None = None
        self.staff_authentication_service: StaffAuthenticationService | None = None
        self.staff_fulfilment_service: StaffFulfilmentService | None = None
        self.staff_order_query_service: StaffOrderQueryService | None = None

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
        self.settings.validate_payment_configuration()
        self.settings.validate_whatsapp_configuration()
        self.settings.validate_notification_configuration()
        self.settings.validate_web_chat_configuration()
        self.settings.validate_staff_configuration()
        self._build_whatsapp()
        await self.database_pool.connect()
        try:
            await self.graph_checkpointer.start()
            self._build_runtime()
            if self.whatsapp_provider_name is not None:
                self.whatsapp_workers_blocked = (
                    await self.channel_repository.has_unresolved_other_provider(
                        self.whatsapp_provider_name
                    )
                )
            self._start_notification_worker()
            self._start_channel_workers()
            self.payment_reconciliation_job.start()
            self.inventory_reconciliation_job.start()
        except Exception:
            if self.channel_inbound_processor is not None:
                await self.channel_inbound_processor.stop()
            if self.channel_outbound_dispatcher is not None:
                await self.channel_outbound_dispatcher.stop()
            if self.notification_outbox_processor is not None:
                await self.notification_outbox_processor.stop()
            if self.notification_reconciliation_job is not None:
                await self.notification_reconciliation_job.stop()
            await self.graph_checkpointer.close()
            await self.database_pool.close()
            if self.meta_http_client is not None:
                await self.meta_http_client.aclose()
            raise

    async def shutdown(self) -> None:
        """
        Shutdown application infrastructure.
        """
        if self.channel_inbound_processor is not None:
            await self.channel_inbound_processor.stop()
        if self.channel_outbound_dispatcher is not None:
            await self.channel_outbound_dispatcher.stop()
        if self.notification_outbox_processor is not None:
            await self.notification_outbox_processor.stop()
        if self.notification_reconciliation_job is not None:
            await self.notification_reconciliation_job.stop()
        await self.payment_reconciliation_job.stop()
        await self.inventory_reconciliation_job.stop()
        if self.meta_http_client is not None:
            await self.meta_http_client.aclose()
        await self.graph_checkpointer.close()
        await self.database_pool.close()

    def _build_infrastructure(self) -> None:
        """
        Construct infrastructure components.
        """

        self.database_pool = DatabasePool(
            config=self.settings.database,
        )
        self.channel_repository = PostgresChannelRepository(self.database_pool)
        self.notification_repository = PostgresNotificationOutboxRepository(
            self.database_pool
        )
        self.notification_templates = NotificationTemplateRegistry(
            version=self.settings.NOTIFICATION_TEMPLATE_REGISTRY_VERSION,
            default_locale=self.settings.NOTIFICATION_DEFAULT_LOCALE,
            content_sids=self.settings.TWILIO_NOTIFICATION_CONTENT_SIDS,
        )
        self.whatsapp_templates = WhatsAppTemplateRegistry(
            content_sids=self.settings.TWILIO_NOTIFICATION_CONTENT_SIDS,
            meta_templates=self.settings.META_NOTIFICATION_TEMPLATES,
        )
        self.chat_request_repository = PostgresChatRequestRepository(self.database_pool)
        self.staff_repository = PostgresStaffRepository(self.database_pool)
        self.staff_order_repository = PostgresStaffOrderRepository(self.database_pool)
        self.staff_catalog_repository = PostgresCatalogAdminRepository(
            self.database_pool, self.settings.STAFF_IDEMPOTENCY_RETENTION_HOURS
        )
        self.inventory_reconciliation_job = InventoryReconciliationJob(
            self.staff_catalog_repository,
            self.settings.INVENTORY_RECONCILIATION_BATCH_SIZE,
            self.settings.INVENTORY_RECONCILIATION_INTERVAL_SECONDS,
        )
        self.staff_rate_limiter = (
            FixedWindowRateLimiter()
            if self.settings.APP_ENV in {"development", "test"}
            else PostgresFixedWindowRateLimiter(self.database_pool)
        )
        if self.settings.STAFF_AUTH_ENABLED:
            public_keys = {
                key_id: value.replace("\\n", "\n")
                for key_id, value in self.settings.STAFF_JWT_PREVIOUS_PUBLIC_KEYS.items()
            }
            public_keys[self.settings.STAFF_JWT_ACTIVE_KEY_ID] = (
                self.settings.STAFF_JWT_PUBLIC_KEY or ""
            ).replace("\\n", "\n")
            token_codec = AccessTokenCodec(
                private_key=(self.settings.STAFF_JWT_PRIVATE_KEY or "").replace(
                    "\\n", "\n"
                ),
                public_keys=public_keys,
                active_key_id=self.settings.STAFF_JWT_ACTIVE_KEY_ID,
                algorithm=self.settings.STAFF_JWT_ALGORITHM,
                issuer=self.settings.STAFF_JWT_ISSUER,
                audience=self.settings.STAFF_JWT_AUDIENCE,
                ttl_seconds=self.settings.STAFF_ACCESS_TOKEN_TTL_SECONDS,
            )
            self.staff_token_codec = token_codec
            self.staff_authentication_service = StaffAuthenticationService(
                self.staff_repository,
                Argon2PasswordHasher(),
                token_codec,
                self.settings.DEFAULT_TENANT_ID,
            )
            self.staff_fulfilment_service = StaffFulfilmentService(
                self.database_pool, self.settings.STAFF_IDEMPOTENCY_RETENTION_HOURS
            )
            self.staff_order_query_service = StaffOrderQueryService(
                self.staff_order_repository
            )
            self.staff_catalog_service = StaffCatalogService(
                self.staff_catalog_repository,
                tuple(
                    value.upper()
                    for value in self.settings.CATALOG_SUPPORTED_CURRENCIES
                ),
                tuple(self.settings.CATALOG_SUPPORTED_UNITS),
            )

    def _build_whatsapp(self) -> None:
        if self.settings.WHATSAPP_PROVIDER == "twilio":
            if (
                not self.settings.TWILIO_AUTH_TOKEN
                or not self.settings.TWILIO_ACCOUNT_SID
            ):
                raise RuntimeError("Twilio configuration was not validated.")
            self.twilio_request_validator = TwilioRequestValidator(
                self.settings.TWILIO_AUTH_TOKEN
            )
            self.twilio_message_provider = TwilioWhatsAppMessageProvider(
                self.settings.TWILIO_ACCOUNT_SID,
                self.settings.TWILIO_AUTH_TOKEN,
                self.settings.TWILIO_WHATSAPP_FROM,
                self.settings.TWILIO_WHATSAPP_MAX_OUTBOUND_BODY_CHARS,
                self.settings.twilio_status_url,
            )
            self.twilio_configured = True
            self.whatsapp_provider = self.twilio_message_provider
            self.whatsapp_provider_name = WhatsAppProviderName.TWILIO
            self.whatsapp_sender_id = self.settings.TWILIO_WHATSAPP_FROM
        elif self.settings.WHATSAPP_PROVIDER == "meta_cloud":
            assert self.settings.META_WHATSAPP_APP_SECRET
            assert self.settings.META_WHATSAPP_BUSINESS_ACCOUNT_ID
            assert self.settings.META_WHATSAPP_PHONE_NUMBER_ID
            assert self.settings.META_WHATSAPP_ACCESS_TOKEN
            self.meta_signature_validator = MetaSignatureValidator(
                self.settings.META_WHATSAPP_APP_SECRET
            )
            self.meta_webhook_parser = MetaWebhookParser(
                waba_id=self.settings.META_WHATSAPP_BUSINESS_ACCOUNT_ID,
                phone_number_id=self.settings.META_WHATSAPP_PHONE_NUMBER_ID,
                max_text_chars=self.settings.META_WHATSAPP_MAX_TEXT_CHARS,
                max_text_bytes=self.settings.META_WHATSAPP_MAX_INBOUND_BODY_BYTES,
            )
            self.meta_http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.settings.META_WHATSAPP_HTTP_TIMEOUT_SECONDS)
            )
            self.meta_message_provider = MetaWhatsAppMessageProvider(
                client=self.meta_http_client,
                graph_api_version=self.settings.META_GRAPH_API_VERSION,
                phone_number_id=self.settings.META_WHATSAPP_PHONE_NUMBER_ID,
                access_token=self.settings.META_WHATSAPP_ACCESS_TOKEN,
                max_text_chars=self.settings.META_WHATSAPP_MAX_TEXT_CHARS,
            )
            self.whatsapp_provider = self.meta_message_provider
            self.whatsapp_provider_name = WhatsAppProviderName.META_CLOUD
            self.whatsapp_sender_id = self.settings.META_WHATSAPP_PHONE_NUMBER_ID

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
        self.payment_repository = PostgresPaymentRepository(pool=self.database_pool)
        self.inventory_repository = PostgresInventoryRepository(
            pool=self.database_pool,
        )
        self.saved_delivery_details_repository = PostgresSavedDeliveryDetailsRepository(
            pool=self.database_pool,
        )

        self.search_product_service = SearchProductService(
            product_repository=self.product_repository,
        )
        self.catalog_browse_service = CatalogBrowseService(
            self.product_repository,
            CatalogBrowsePolicy(
                product_page_size=self.settings.CATALOG_BROWSE_PRODUCT_PAGE_SIZE,
                category_page_size=self.settings.CATALOG_BROWSE_CATEGORY_PAGE_SIZE,
                direct_product_limit=self.settings.CATALOG_BROWSE_DIRECT_PRODUCT_LIMIT,
                hide_empty_categories=self.settings.CATALOG_HIDE_EMPTY_CATEGORIES,
            ),
        )

        self.cart_service = CartService(repository=self.cart_repository)
        self.direct_cart_service = DirectCartService(
            self.product_repository, self.cart_repository
        )
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
        self.saved_delivery_details_service = SavedDeliveryDetailsService(
            repository=self.saved_delivery_details_repository,
            phone_policy=self.phone_validation_policy,
        )
        self.payment_provider = FakePaymentProvider(
            pool=self.database_pool,
            base_url=self.settings.FAKE_PAYMENT_BASE_URL,
            webhook_secret=self.settings.FAKE_PAYMENT_WEBHOOK_SECRET or "test-secret",
        )
        self.payment_service = PaymentService(
            repository=self.payment_repository,
            provider=self.payment_provider,
            ttl_minutes=self.settings.PAYMENT_ATTEMPT_TTL_MINUTES,
            return_url=f"{self.settings.FAKE_PAYMENT_BASE_URL.rstrip('/')}/chat",
        )
        self.payment_event_service = PaymentEventService(
            self.payment_repository, self.payment_provider
        )
        self.payment_reconciliation_job = PaymentReconciliationJob(
            self.payment_repository,
            self.payment_provider,
            self.payment_event_service,
            self.payment_service,
            self.settings.PAYMENT_RECONCILIATION_BATCH_SIZE,
            self.settings.PAYMENT_RECONCILIATION_INTERVAL_SECONDS,
        )

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
        self.start_customer_onboarding_capability = StartCustomerOnboardingCapability(
            self.saved_delivery_details_service
        )
        self.collect_customer_onboarding_details_capability = (
            CollectCustomerOnboardingDetailsCapability(self.phone_validation_policy)
        )
        self.confirm_customer_onboarding_capability = (
            ConfirmCustomerOnboardingCapability(self.saved_delivery_details_service)
        )
        self.skip_customer_onboarding_capability = SkipCustomerOnboardingCapability()
        self.start_customer_shopping_capability = StartCustomerShoppingCapability(
            self.catalog_browse_service, self.customer_journey_observer
        )

        self.search_product_capability = SearchProductCapability(
            service=self.search_product_service,
        )

        self.select_product_capability = SelectProductCapability()
        self.browse_catalog_capability = BrowseCatalogCapability(
            self.catalog_browse_service, observer=self.customer_journey_observer
        )
        self.resolve_catalog_browse_capability = ResolveCatalogBrowseCapability(
            self.catalog_browse_service,
            ttl=timedelta(seconds=self.settings.CATALOG_BROWSE_STATE_TTL_SECONDS),
            observer=self.customer_journey_observer,
        )

        self.add_to_cart_capability = AddToCartCapability(
            service=self.cart_service,
        )
        self.add_product_to_cart_capability = AddProductToCartCapability(
            self.direct_cart_service
        )
        self.select_pending_cart_product_capability = (
            ResolvePendingCartAdditionCapability(
                self.direct_cart_service,
                ttl=timedelta(minutes=self.settings.PENDING_CART_ADDITION_TTL_MINUTES),
            )
        )

        self.view_cart_capability = ViewCartCapability(service=self.cart_service)

        self.remove_from_cart_capability = RemoveFromCartCapability(
            service=self.cart_service,
        )
        self.update_cart_item_quantity_capability = UpdateCartItemQuantityCapability(
            service=self.cart_service,
        )
        self.accept_available_quantity_capability = AcceptAvailableQuantityCapability(
            service=self.cart_service,
        )
        self.clear_cart_capability = ClearCartCapability(service=self.cart_service)
        self.checkout_capability = CheckoutCapability(
            service=self.cart_service,
            saved_details_service=self.saved_delivery_details_service,
        )
        self.collect_delivery_details_capability = CollectDeliveryDetailsCapability(
            phone_policy=self.phone_validation_policy,
        )
        self.update_delivery_details_capability = UpdateDeliveryDetailsCapability(
            cart_service=self.cart_service,
            phone_policy=self.phone_validation_policy,
        )
        self.abandon_checkout_capability = AbandonCheckoutCapability()
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
        self.list_saved_addresses_capability = ListSavedAddressesCapability(
            self.saved_delivery_details_service
        )
        self.view_saved_delivery_profile_capability = (
            ViewSavedDeliveryProfileCapability(self.saved_delivery_details_service)
        )
        self.select_saved_address_capability = SelectSavedAddressCapability(
            self.saved_delivery_details_service
        )
        self.save_delivery_details_capability = SaveDeliveryDetailsCapability(
            self.saved_delivery_details_service
        )
        self.confirm_save_delivery_details_capability = (
            ConfirmSaveDeliveryDetailsCapability(self.saved_delivery_details_service)
        )
        self.confirm_saved_profile_use_capability = ConfirmSavedProfileUseCapability(
            self.saved_delivery_details_service
        )
        self.update_saved_address_capability = UpdateSavedAddressCapability(
            self.saved_delivery_details_service
        )
        self.delete_saved_address_capability = DeleteSavedAddressCapability(
            self.saved_delivery_details_service
        )
        self.set_default_address_capability = SetDefaultAddressCapability(
            self.saved_delivery_details_service
        )
        self.select_payment_method_capability = SelectPaymentMethodCapability()
        self.start_online_payment_capability = StartOnlinePaymentCapability(
            self.payment_service
        )
        self.retry_online_payment_capability = RetryOnlinePaymentCapability(
            self.payment_service
        )
        self.switch_order_to_cod_capability = SwitchOrderToCashOnDeliveryCapability(
            self.payment_service
        )
        self.view_payment_status_capability = ViewPaymentStatusCapability(
            self.payment_service
        )

        self.capability_registry = CapabilityRegistry[CommerceSession](
            capabilities=[
                self.greeting_capability,
                self.start_customer_onboarding_capability,
                self.collect_customer_onboarding_details_capability,
                self.confirm_customer_onboarding_capability,
                self.skip_customer_onboarding_capability,
                self.start_customer_shopping_capability,
                self.search_product_capability,
                self.select_product_capability,
                self.browse_catalog_capability,
                self.resolve_catalog_browse_capability,
                self.add_to_cart_capability,
                self.add_product_to_cart_capability,
                self.select_pending_cart_product_capability,
                self.view_cart_capability,
                self.remove_from_cart_capability,
                self.update_cart_item_quantity_capability,
                self.accept_available_quantity_capability,
                self.clear_cart_capability,
                self.checkout_capability,
                self.collect_delivery_details_capability,
                self.update_delivery_details_capability,
                self.abandon_checkout_capability,
                self.confirm_order_capability,
                self.get_order_status_capability,
                self.list_orders_capability,
                self.get_order_details_capability,
                self.cancel_order_capability,
                self.list_saved_addresses_capability,
                self.view_saved_delivery_profile_capability,
                self.select_saved_address_capability,
                self.save_delivery_details_capability,
                self.confirm_save_delivery_details_capability,
                self.confirm_saved_profile_use_capability,
                self.update_saved_address_capability,
                self.delete_saved_address_capability,
                self.set_default_address_capability,
                self.select_payment_method_capability,
                self.start_online_payment_capability,
                self.retry_online_payment_capability,
                self.switch_order_to_cod_capability,
                self.view_payment_status_capability,
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
            deferred_intent_ttl=timedelta(
                seconds=self.settings.CUSTOMER_DEFERRED_INTENT_TTL_SECONDS
            ),
            customer_journey_observer=self.customer_journey_observer,
        )

        self.runtime = CommerceRuntime(
            graph=self.commerce_graph,
            graph_state_adapter=self.graph_state_adapter,
            saved_delivery_details_service=self.saved_delivery_details_service,
        )

    def _start_channel_workers(self) -> None:
        if (
            self.whatsapp_provider is None
            or self.whatsapp_provider_name is None
            or self.whatsapp_sender_id is None
            or not self.settings.WHATSAPP_PROCESSOR_ENABLED
            or self.whatsapp_workers_blocked
        ):
            return
        common = {
            "repository": self.channel_repository,
            "batch_size": self.settings.WHATSAPP_PROCESSOR_BATCH_SIZE,
            "lease_seconds": self.settings.WHATSAPP_LEASE_SECONDS,
            "max_attempts": self.settings.WHATSAPP_MAX_ATTEMPTS,
            "interval_seconds": self.settings.WHATSAPP_PROCESSOR_INTERVAL_SECONDS,
            "provider_name": self.whatsapp_provider_name,
        }
        self.channel_inbound_processor = ChannelInboundProcessor(
            runtime=self.runtime,
            sender_id=self.whatsapp_sender_id,
            response_generator=self.response_generator,
            **common,
        )
        self.channel_outbound_dispatcher = ChannelOutboundDispatcher(
            provider=self.whatsapp_provider,
            window_hours=self.settings.WHATSAPP_CUSTOMER_SERVICE_WINDOW_HOURS,
            notification_templates=self.notification_templates,
            provider_templates=self.whatsapp_templates,
            **common,
        )
        self.channel_inbound_processor.start()
        self.channel_outbound_dispatcher.start()

    def _start_notification_worker(self) -> None:
        if not (
            self.settings.CUSTOMER_NOTIFICATIONS_ENABLED
            and self.settings.NOTIFICATION_PROCESSOR_ENABLED
        ):
            return
        if self.whatsapp_workers_blocked:
            return
        if self.whatsapp_provider_name is not None:
            self.whatsapp_templates.validate(
                self.whatsapp_provider_name, self.notification_templates.locales
            )
        self.notification_outbox_processor = NotificationOutboxProcessor(
            repository=self.notification_repository,
            channel_repository=self.channel_repository,
            templates=self.notification_templates,
            provider_templates=self.whatsapp_templates,
            sender_id=self.whatsapp_sender_id or "disabled",
            batch_size=self.settings.NOTIFICATION_PROCESSOR_BATCH_SIZE,
            lease_seconds=self.settings.NOTIFICATION_PROCESSOR_LEASE_SECONDS,
            max_attempts=self.settings.NOTIFICATION_PROCESSOR_MAX_ATTEMPTS,
            max_retry_delay_seconds=self.settings.NOTIFICATION_RETRY_MAX_DELAY_SECONDS,
            interval_seconds=self.settings.NOTIFICATION_PROCESSOR_INTERVAL_SECONDS,
            window_hours=self.settings.WHATSAPP_CUSTOMER_SERVICE_WINDOW_HOURS,
            whatsapp_enabled=self.whatsapp_provider is not None,
            provider_name=self.whatsapp_provider_name or WhatsAppProviderName.TWILIO,
        )
        self.notification_outbox_processor.start()
        self.notification_reconciliation_job = NotificationReconciliationJob(
            repository=self.notification_repository,
            batch_size=self.settings.NOTIFICATION_RECONCILIATION_BATCH_SIZE,
            interval_seconds=self.settings.NOTIFICATION_RECONCILIATION_INTERVAL_SECONDS,
        )
        self.notification_reconciliation_job.start()

import re
from typing import Literal
from uuid import UUID

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from infrastructure.database.config import DatabaseConfig


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    LLM_PROVIDER: Literal["ollama", "gemini"]

    OLLAMA_BASE_URL: str
    OLLAMA_MODEL: str

    GEMINI_API_KEY: str
    GEMINI_MODEL: str

    LLM_TEMPERATURE: float
    LLM_MAX_TOKENS: int

    POSTGRES_HOST: str
    POSTGRES_PORT: int
    POSTGRES_DB: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str

    DEFAULT_TENANT_ID: UUID
    CHECKPOINTER_BACKEND: Literal["memory", "postgres"]
    CUSTOMER_SUPPORT_PATH: str = Field(min_length=1)
    ALLOW_DEVELOPMENT_CUSTOMER_ID_HEADER: bool = True
    WEB_CHAT_ALLOWED_ORIGINS: list[str] = ["http://localhost:5173"]
    APP_ENV: Literal["development", "test", "production"] = "development"
    PAYMENT_PROVIDER: Literal["fake"] = "fake"
    FAKE_PAYMENT_WEBHOOK_SECRET: str | None = None
    FAKE_PAYMENT_BASE_URL: str = "http://localhost:8000"
    PAYMENT_ATTEMPT_TTL_MINUTES: int = Field(default=15, ge=1)
    PENDING_CART_ADDITION_TTL_MINUTES: int = Field(default=15, ge=1, le=1440)
    CATALOG_BROWSE_PRODUCT_PAGE_SIZE: int = Field(default=10, ge=1, le=100)
    CATALOG_BROWSE_CATEGORY_PAGE_SIZE: int = Field(default=10, ge=1, le=100)
    CATALOG_BROWSE_DIRECT_PRODUCT_LIMIT: int = Field(default=10, ge=1, le=1000)
    CATALOG_BROWSE_STATE_TTL_SECONDS: int = Field(default=900, ge=1, le=86400)
    CUSTOMER_DEFERRED_INTENT_TTL_SECONDS: int = Field(default=900, ge=1, le=86400)
    CATALOG_HIDE_EMPTY_CATEGORIES: bool = True
    PAYMENT_RECONCILIATION_BATCH_SIZE: int = Field(default=100, ge=1, le=1000)
    PAYMENT_RECONCILIATION_INTERVAL_SECONDS: int = Field(default=30, ge=1)
    PAYMENT_WEBHOOK_RATE_LIMIT_PER_MINUTE: int = Field(default=30, ge=1)
    FAKE_PAYMENT_RATE_LIMIT_PER_MINUTE: int = Field(default=10, ge=1)
    WHATSAPP_PROVIDER: Literal["disabled", "twilio", "meta_cloud"] = "disabled"
    TWILIO_ACCOUNT_SID: str | None = None
    TWILIO_AUTH_TOKEN: str | None = None
    TWILIO_WHATSAPP_FROM: str = "whatsapp:+14155238886"
    TWILIO_WHATSAPP_PUBLIC_BASE_URL: str | None = None
    TWILIO_WHATSAPP_INBOUND_PATH: str = "/webhooks/twilio/whatsapp"
    TWILIO_WHATSAPP_STATUS_PATH: str = "/webhooks/twilio/whatsapp/status"
    TWILIO_WHATSAPP_MAX_INBOUND_BODY_BYTES: int = Field(default=4096, ge=1)
    TWILIO_WHATSAPP_MAX_OUTBOUND_BODY_CHARS: int = Field(default=1600, ge=1)
    WHATSAPP_PROCESSOR_ENABLED: bool = True
    WHATSAPP_PROCESSOR_INTERVAL_SECONDS: float = Field(default=1, gt=0)
    WHATSAPP_PROCESSOR_BATCH_SIZE: int = Field(default=20, ge=1, le=500)
    WHATSAPP_MAX_ATTEMPTS: int = Field(default=5, ge=1, le=20)
    WHATSAPP_LEASE_SECONDS: int = Field(default=120, ge=10)
    WHATSAPP_CUSTOMER_SERVICE_WINDOW_HOURS: int = Field(default=24, ge=1)
    META_GRAPH_API_VERSION: str = "v25.0"
    META_WHATSAPP_PHONE_NUMBER_ID: str | None = None
    META_WHATSAPP_BUSINESS_ACCOUNT_ID: str | None = None
    META_WHATSAPP_ACCESS_TOKEN: str | None = None
    META_WHATSAPP_APP_SECRET: str | None = None
    META_WHATSAPP_VERIFY_TOKEN: str | None = None
    META_WHATSAPP_PUBLIC_BASE_URL: str | None = None
    META_WHATSAPP_WEBHOOK_PATH: str = "/webhooks/meta/whatsapp"
    META_WHATSAPP_HTTP_TIMEOUT_SECONDS: float = Field(default=15, gt=0, le=60)
    META_WHATSAPP_MAX_INBOUND_BODY_BYTES: int = Field(default=65536, ge=1)
    META_WHATSAPP_MAX_TEXT_CHARS: int = Field(default=4096, ge=1, le=4096)
    # Delivery is opt-in because approved provider template identifiers are
    # deployment-owned and cannot have safe application defaults. Business
    # transactions still append durable notification intents while this is off.
    CUSTOMER_NOTIFICATIONS_ENABLED: bool = False
    NOTIFICATION_PROCESSOR_ENABLED: bool = True
    NOTIFICATION_PROCESSOR_INTERVAL_SECONDS: float = Field(default=1, gt=0)
    NOTIFICATION_PROCESSOR_BATCH_SIZE: int = Field(default=20, ge=1, le=500)
    NOTIFICATION_PROCESSOR_LEASE_SECONDS: int = Field(default=120, ge=10)
    NOTIFICATION_PROCESSOR_MAX_ATTEMPTS: int = Field(default=5, ge=1, le=20)
    NOTIFICATION_RETRY_MAX_DELAY_SECONDS: int = Field(default=300, ge=1)
    NOTIFICATION_RECONCILIATION_INTERVAL_SECONDS: int = Field(default=60, ge=1)
    NOTIFICATION_RECONCILIATION_BATCH_SIZE: int = Field(default=100, ge=1, le=1000)
    NOTIFICATION_DEFAULT_LOCALE: str = "en-IN"
    NOTIFICATION_TEMPLATE_REGISTRY_VERSION: int = Field(default=1, ge=1)
    TWILIO_NOTIFICATION_CONTENT_SIDS: dict[str, str] = {}
    META_NOTIFICATION_TEMPLATES: dict[str, dict[str, str]] = {}
    PAYMENT_NOTIFICATIONS_ENABLED: bool = False
    STAFF_AUTH_ENABLED: bool = False
    STAFF_JWT_PRIVATE_KEY: str | None = None
    STAFF_JWT_PUBLIC_KEY: str | None = None
    STAFF_JWT_PREVIOUS_PUBLIC_KEYS: dict[str, str] = {}
    STAFF_JWT_ACTIVE_KEY_ID: str = "primary"
    STAFF_JWT_ALGORITHM: str = "RS256"
    STAFF_JWT_ISSUER: str = "commerce-agent"
    STAFF_JWT_AUDIENCE: str = "commerce-staff"
    STAFF_ACCESS_TOKEN_TTL_SECONDS: int = Field(default=900, ge=60, le=3600)
    STAFF_PASSWORD_MIN_LENGTH: int = Field(default=12, ge=8, le=256)
    STAFF_LOGIN_RATE_LIMIT: int = Field(default=5, ge=1)
    STAFF_API_RATE_LIMIT: int = Field(default=120, ge=1)
    STAFF_IDEMPOTENCY_RETENTION_HOURS: int = Field(default=24, ge=1)
    CATALOG_SUPPORTED_CURRENCIES: list[str] = ["INR"]
    CATALOG_SUPPORTED_UNITS: list[str] = ["kg", "piece"]
    INVENTORY_RECONCILIATION_INTERVAL_SECONDS: int = Field(default=300, ge=10)
    INVENTORY_RECONCILIATION_BATCH_SIZE: int = Field(default=100, ge=1, le=1000)

    def validate_payment_configuration(self) -> None:
        if self.APP_ENV == "production" and self.PAYMENT_PROVIDER == "fake":
            raise RuntimeError("Fake payments are disabled in production.")
        placeholders = {None, "", "replace-with-a-random-development-secret"}
        if self.APP_ENV != "test" and self.FAKE_PAYMENT_WEBHOOK_SECRET in placeholders:
            raise RuntimeError(
                "A non-placeholder fake payment webhook secret is required."
            )

    def validate_twilio_configuration(self) -> None:
        if self.WHATSAPP_PROVIDER != "twilio":
            return
        if not self.TWILIO_ACCOUNT_SID or not self.TWILIO_ACCOUNT_SID.startswith("AC"):
            raise RuntimeError("A valid Twilio Account SID is required.")
        if not self.TWILIO_AUTH_TOKEN:
            raise RuntimeError("A Twilio Auth Token is required.")
        if not self.TWILIO_WHATSAPP_FROM.startswith("whatsapp:+"):
            raise RuntimeError("TWILIO_WHATSAPP_FROM must be a WhatsApp E.164 address.")
        if not self.TWILIO_WHATSAPP_PUBLIC_BASE_URL:
            raise RuntimeError("A Twilio public base URL is required.")
        parsed = AnyHttpUrl(self.TWILIO_WHATSAPP_PUBLIC_BASE_URL)
        if parsed.scheme != "https" and self.APP_ENV != "test":
            raise RuntimeError("The Twilio public base URL must use HTTPS.")
        if self.TWILIO_WHATSAPP_INBOUND_PATH != "/webhooks/twilio/whatsapp":
            raise RuntimeError("The Twilio inbound webhook path is fixed.")
        if self.TWILIO_WHATSAPP_STATUS_PATH != "/webhooks/twilio/whatsapp/status":
            raise RuntimeError("The Twilio status webhook path is fixed.")

    def validate_whatsapp_configuration(self) -> None:
        if self.WHATSAPP_PROVIDER == "disabled":
            return
        if self.WHATSAPP_PROVIDER == "twilio":
            self.validate_twilio_configuration()
            return
        required = {
            "Phone Number ID": self.META_WHATSAPP_PHONE_NUMBER_ID,
            "WABA ID": self.META_WHATSAPP_BUSINESS_ACCOUNT_ID,
            "access token": self.META_WHATSAPP_ACCESS_TOKEN,
            "App Secret": self.META_WHATSAPP_APP_SECRET,
            "verification token": self.META_WHATSAPP_VERIFY_TOKEN,
            "public base URL": self.META_WHATSAPP_PUBLIC_BASE_URL,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuntimeError(
                "Missing Meta WhatsApp configuration: " + ", ".join(missing)
            )
        for label, value in (
            ("Phone Number ID", self.META_WHATSAPP_PHONE_NUMBER_ID),
            ("WABA ID", self.META_WHATSAPP_BUSINESS_ACCOUNT_ID),
        ):
            if value is None or not value.isdigit() or len(value) > 32:
                raise RuntimeError(
                    f"Meta WhatsApp {label} must be a bounded digit string."
                )
        if (
            re.fullmatch(r"v[0-9]{1,3}\.[0-9]{1,2}", self.META_GRAPH_API_VERSION)
            is None
        ):
            raise RuntimeError("META_GRAPH_API_VERSION must be explicitly versioned.")
        if len(self.META_WHATSAPP_VERIFY_TOKEN or "") < 12:
            raise RuntimeError("The Meta verification token must be high entropy.")
        if len(self.META_WHATSAPP_APP_SECRET or "") < 16:
            raise RuntimeError("The Meta App Secret is malformed.")
        if len(self.META_WHATSAPP_ACCESS_TOKEN or "") > 8192:
            raise RuntimeError("The Meta access token is too large.")
        assert self.META_WHATSAPP_PUBLIC_BASE_URL is not None
        parsed = AnyHttpUrl(self.META_WHATSAPP_PUBLIC_BASE_URL)
        if parsed.scheme != "https" and self.APP_ENV != "test":
            raise RuntimeError("The Meta WhatsApp public base URL must use HTTPS.")
        if self.META_WHATSAPP_WEBHOOK_PATH != "/webhooks/meta/whatsapp":
            raise RuntimeError("The Meta WhatsApp webhook path is fixed.")

    def validate_notification_configuration(self) -> None:
        if self.PAYMENT_NOTIFICATIONS_ENABLED:
            raise RuntimeError(
                "Payment notifications require a production payment provider."
            )
        if not self.CUSTOMER_NOTIFICATIONS_ENABLED:
            return
        if not self.NOTIFICATION_DEFAULT_LOCALE.strip():
            raise RuntimeError("A notification default locale is required.")

    def validate_web_chat_configuration(self) -> None:
        if not self.WEB_CHAT_ALLOWED_ORIGINS:
            raise RuntimeError("At least one web chat origin is required.")
        for origin in self.WEB_CHAT_ALLOWED_ORIGINS:
            parsed = AnyHttpUrl(origin)
            if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
                raise RuntimeError("Web chat origins must not contain a path.")
            if self.APP_ENV == "production" and parsed.scheme != "https":
                raise RuntimeError("Production web chat origins must use HTTPS.")

    def validate_staff_configuration(self) -> None:
        if not self.STAFF_AUTH_ENABLED:
            return
        if not self.STAFF_JWT_PRIVATE_KEY or not self.STAFF_JWT_PUBLIC_KEY:
            raise RuntimeError("Staff JWT signing and verification keys are required.")
        if self.STAFF_JWT_ALGORITHM not in {
            "RS256",
            "RS384",
            "RS512",
            "ES256",
            "ES384",
        }:
            raise RuntimeError(
                "Staff JWT algorithm must be an approved asymmetric algorithm."
            )
        if not self.STAFF_JWT_ACTIVE_KEY_ID.strip():
            raise RuntimeError("A staff JWT active key ID is required.")
        if not self.STAFF_JWT_ISSUER.strip() or not self.STAFF_JWT_AUDIENCE.strip():
            raise RuntimeError("Staff JWT issuer and audience are required.")

    @property
    def twilio_public_base_url(self) -> str:
        if not self.TWILIO_WHATSAPP_PUBLIC_BASE_URL:
            raise RuntimeError("Twilio is not configured.")
        return self.TWILIO_WHATSAPP_PUBLIC_BASE_URL.rstrip("/")

    @property
    def twilio_inbound_url(self) -> str:
        return f"{self.twilio_public_base_url}{self.TWILIO_WHATSAPP_INBOUND_PATH}"

    @property
    def twilio_status_url(self) -> str:
        return f"{self.twilio_public_base_url}{self.TWILIO_WHATSAPP_STATUS_PATH}"

    @property
    def meta_whatsapp_webhook_url(self) -> str:
        if not self.META_WHATSAPP_PUBLIC_BASE_URL:
            raise RuntimeError("Meta WhatsApp is not configured.")
        return f"{self.META_WHATSAPP_PUBLIC_BASE_URL.rstrip('/')}{self.META_WHATSAPP_WEBHOOK_PATH}"

    @property
    def database(self) -> DatabaseConfig:
        return DatabaseConfig(
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            database=self.POSTGRES_DB,
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
        )


settings = Settings()  # type: ignore[call-arg]

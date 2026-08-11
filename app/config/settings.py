from typing import Literal
from uuid import UUID

from pydantic import Field
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
    ALLOW_DEVELOPMENT_CUSTOMER_ID_HEADER: bool = False
    APP_ENV: Literal["development", "test", "production"] = "development"
    PAYMENT_PROVIDER: Literal["fake"] = "fake"
    FAKE_PAYMENT_WEBHOOK_SECRET: str | None = None
    FAKE_PAYMENT_BASE_URL: str = "http://localhost:8000"
    PAYMENT_ATTEMPT_TTL_MINUTES: int = Field(default=15, ge=1)
    PAYMENT_RECONCILIATION_BATCH_SIZE: int = Field(default=100, ge=1, le=1000)
    PAYMENT_RECONCILIATION_INTERVAL_SECONDS: int = Field(default=30, ge=1)
    PAYMENT_WEBHOOK_RATE_LIMIT_PER_MINUTE: int = Field(default=30, ge=1)
    FAKE_PAYMENT_RATE_LIMIT_PER_MINUTE: int = Field(default=10, ge=1)

    def validate_payment_configuration(self) -> None:
        if self.APP_ENV == "production" and self.PAYMENT_PROVIDER == "fake":
            raise RuntimeError("Fake payments are disabled in production.")
        placeholders = {None, "", "replace-with-a-random-development-secret"}
        if self.APP_ENV != "test" and self.FAKE_PAYMENT_WEBHOOK_SECRET in placeholders:
            raise RuntimeError(
                "A non-placeholder fake payment webhook secret is required."
            )

    @property
    def database(self) -> DatabaseConfig:
        return DatabaseConfig(
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            database=self.POSTGRES_DB,
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
        )


settings = Settings()

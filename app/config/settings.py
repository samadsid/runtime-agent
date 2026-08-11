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

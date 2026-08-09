from pydantic import BaseModel, ConfigDict


class DatabaseConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    host: str
    port: int
    database: str
    username: str
    password: str

    @property
    def dsn(self) -> str:
        return (
            f"postgresql://"
            f"{self.username}:{self.password}"
            f"@{self.host}:{self.port}"
            f"/{self.database}"
        )

    @property
    def sqlalchemy_async_dsn(self) -> str:
        return self.dsn.replace("postgresql://", "postgresql+asyncpg://", 1)

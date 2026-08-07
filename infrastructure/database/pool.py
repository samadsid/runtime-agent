from __future__ import annotations

import asyncpg

from infrastructure.database.config import DatabaseConfig


class DatabasePool:
    def __init__(
        self,
        config: DatabaseConfig,
    ) -> None:
        self._config = config
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        if self._pool is not None:
            return

        self._pool = await asyncpg.create_pool(
            dsn=self._config.dsn,
            min_size=2,
            max_size=10,
        )
        print("[Database] Connection pool initialized.")

    async def close(self) -> None:
        if self._pool is None:
            return

        await self._pool.close()
        self._pool = None

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError(
                "Database pool has not been initialized."
            )

        return self._pool
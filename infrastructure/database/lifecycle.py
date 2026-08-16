from infrastructure.database.pool import DatabasePool


class DatabaseLifecycle:

    def __init__(
        self,
        pool: DatabasePool,
    ) -> None:
        self._pool = pool

    async def startup(self) -> None:
        await self._pool.connect()

    async def shutdown(self) -> None:
        await self._pool.close()

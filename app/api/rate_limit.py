from __future__ import annotations

import asyncio
import time


class FixedWindowRateLimiter:
    """Small process-local guard for development endpoints.

    Production payment endpoints still require distributed edge rate limiting.
    """

    def __init__(self) -> None:
        self._windows: dict[str, tuple[float, int]] = {}
        self._lock = asyncio.Lock()

    async def allow(self, key: str, limit: int, window_seconds: int = 60) -> bool:
        now = time.monotonic()
        async with self._lock:
            started, count = self._windows.get(key, (now, 0))
            if now - started >= window_seconds:
                started, count = now, 0
            if count >= limit:
                return False
            self._windows[key] = (started, count + 1)
            return True

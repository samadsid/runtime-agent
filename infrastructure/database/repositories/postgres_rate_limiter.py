from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256

from infrastructure.database import DatabasePool


class PostgresFixedWindowRateLimiter:
    def __init__(self, pool: DatabasePool) -> None:
        self._pool = pool

    async def allow(self, key: str, limit: int, window_seconds: int = 60) -> bool:
        bucket = sha256(key.encode()).hexdigest()
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=window_seconds)
        expires = now + timedelta(seconds=window_seconds)
        row = await self._pool.pool.fetchrow(
            """INSERT INTO staff_rate_limit_buckets
                   (bucket_key,window_started_at,request_count,expires_at)
               VALUES ($1,$2,1,$3)
               ON CONFLICT (bucket_key) DO UPDATE SET
                 window_started_at=CASE WHEN staff_rate_limit_buckets.window_started_at <= $4
                                        THEN $2 ELSE staff_rate_limit_buckets.window_started_at END,
                 request_count=CASE WHEN staff_rate_limit_buckets.window_started_at <= $4
                                    THEN 1 ELSE staff_rate_limit_buckets.request_count+1 END,
                 expires_at=CASE WHEN staff_rate_limit_buckets.window_started_at <= $4
                                 THEN $3 ELSE staff_rate_limit_buckets.expires_at END
               RETURNING request_count""",
            bucket, now, expires, cutoff,
        )
        return bool(row and row["request_count"] <= limit)

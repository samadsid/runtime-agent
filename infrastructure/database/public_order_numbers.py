from __future__ import annotations

import asyncpg


async def allocate_public_order_number(
    connection: asyncpg.Connection,
    *,
    prefix: str,
    business_timezone: str,
) -> str:
    value = await connection.fetchval(
        """
        SELECT $1 || '-' || to_char(now() AT TIME ZONE $2, 'YYMMDD') || '-' ||
               lpad(nextval('public_order_number_seq')::text, 4, '0')
        """,
        prefix,
        business_timezone,
    )
    if not isinstance(value, str):
        raise TypeError("Public order number allocation returned an invalid value.")
    return value

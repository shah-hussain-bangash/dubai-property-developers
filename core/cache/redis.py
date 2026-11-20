
"""Redis client factory and health probe (redis-py asyncio)."""

from __future__ import annotations

from typing import Any

from core.config.settings import Settings


def create_redis_client(settings: Settings) -> Any:
    from redis.asyncio import Redis

    return Redis.from_url(
        settings.redis_url.get_secret_value(),
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=15,
    )


async def ping_redis(settings: Settings) -> bool:
    client = create_redis_client(settings)
    try:
        return bool(await client.ping())
    except Exception:
        return False
    finally:
        await client.aclose()

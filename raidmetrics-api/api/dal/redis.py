import os

import redis.asyncio as aioredis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Module-level client — from_url creates a connection pool internally
_client: aioredis.Redis = aioredis.from_url(REDIS_URL, decode_responses=True)


def get_redis() -> aioredis.Redis:
    return _client

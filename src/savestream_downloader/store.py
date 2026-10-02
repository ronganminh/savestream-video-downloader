from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Protocol

from redis.asyncio import Redis


class Store(Protocol):
    name: str

    async def get_json(self, key: str) -> dict[str, Any] | None: ...
    async def set_json(self, key: str, value: dict[str, Any], ttl: int) -> None: ...
    async def incr(self, key: str, ttl: int) -> int: ...
    async def close(self) -> None: ...


class MemoryStore:
    name = "memory"

    def __init__(self) -> None:
        self._values: dict[str, tuple[float, str]] = {}
        self._counters: dict[str, tuple[float, int]] = {}
        self._lock = asyncio.Lock()

    async def get_json(self, key: str) -> dict[str, Any] | None:
        async with self._lock:
            item = self._values.get(key)
            if not item:
                return None
            expires_at, raw = item
            if expires_at <= time.time():
                self._values.pop(key, None)
                return None
            return json.loads(raw)

    async def set_json(self, key: str, value: dict[str, Any], ttl: int) -> None:
        raw = json.dumps(value, separators=(",", ":"))
        async with self._lock:
            self._values[key] = (time.time() + ttl, raw)

    async def incr(self, key: str, ttl: int) -> int:
        now = time.time()
        async with self._lock:
            expires_at, count = self._counters.get(key, (now + ttl, 0))
            if expires_at <= now:
                expires_at, count = now + ttl, 0
            count += 1
            self._counters[key] = (expires_at, count)
            return count

    async def close(self) -> None:
        return None


class RedisStore:
    name = "redis"

    def __init__(self, client: Redis) -> None:
        self._client = client

    async def get_json(self, key: str) -> dict[str, Any] | None:
        raw = await self._client.get(key)
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)

    async def set_json(self, key: str, value: dict[str, Any], ttl: int) -> None:
        await self._client.set(key, json.dumps(value, separators=(",", ":")), ex=ttl)

    async def incr(self, key: str, ttl: int) -> int:
        pipe = self._client.pipeline()
        pipe.incr(key)
        pipe.expire(key, ttl, nx=True)
        result = await pipe.execute()
        return int(result[0])

    async def close(self) -> None:
        await self._client.aclose()


async def create_store(redis_url: str | None) -> Store:
    if not redis_url:
        return MemoryStore()
    client = Redis.from_url(redis_url, decode_responses=False, socket_connect_timeout=1.5)
    try:
        await client.ping()
    except Exception:
        await client.aclose()
        return MemoryStore()
    return RedisStore(client)

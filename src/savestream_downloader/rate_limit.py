from __future__ import annotations

from fastapi import HTTPException

from .store import Store


class RateLimiter:
    def __init__(self, store: Store) -> None:
        self._store = store

    async def check(self, bucket: str, limit: int, window_seconds: int = 60) -> None:
        if limit <= 0:
            return
        count = await self._store.incr(f"rate:{bucket}", window_seconds)
        if count > limit:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    value: T
    expires_at: datetime


class TTLCache(Generic[T]):
    def __init__(self, ttl_seconds: int = 900, max_items: int = 256) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_items = max_items
        self._store: dict[str, CacheEntry[T]] = {}

    def get(self, key: str) -> T | None:
        item = self._store.get(key)
        now = datetime.now(timezone.utc)
        if item is None:
            return None
        if item.expires_at <= now:
            self._store.pop(key, None)
            return None
        return item.value

    def set(self, key: str, value: T) -> None:
        now = datetime.now(timezone.utc)
        if len(self._store) >= self.max_items:
            oldest_key = min(self._store, key=lambda k: self._store[k].expires_at)
            self._store.pop(oldest_key, None)
        self._store[key] = CacheEntry(value=value, expires_at=now + timedelta(seconds=self.ttl_seconds))

    def clear(self) -> None:
        self._store.clear()

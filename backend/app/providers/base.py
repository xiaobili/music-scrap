from __future__ import annotations

import asyncio
import hashlib
import time
from abc import ABC
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Awaitable, Callable

import httpx
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db.models import ProviderCache
from ..services.settings import SettingsStore


class Capability(str, Enum):
    SEARCH_RELEASE = "search_release"
    GET_RELEASE = "get_release"
    COVER = "cover"
    FINGERPRINT = "fingerprint"


class CoverCandidate(BaseModel):
    provider: str
    url: str
    width: int | None = None
    height: int | None = None


class CanonicalTrack(BaseModel):
    position: int
    disc: int = 1
    title: str
    artist: str | None = None
    duration_ms: int | None = None
    isrc: str | None = None
    mbid: str | None = None


class CanonicalRelease(BaseModel):
    provider: str
    provider_id: str
    title: str
    artist: str | None = None
    year: int | None = None
    label: str | None = None
    catalog_number: str | None = None
    barcode: str | None = None
    genres: list[str] = Field(default_factory=list)
    country: str | None = None
    format: str | None = None
    release_mbid: str | None = None
    release_group_mbid: str | None = None
    tracks: list[CanonicalTrack] = Field(default_factory=list)
    covers: list[CoverCandidate] = Field(default_factory=list)


class ReleaseQuery(BaseModel):
    album: str | None = None
    artist: str | None = None
    year: int | None = None
    track_count: int | None = None
    mbid: str | None = None


class ProviderError(Exception):
    pass


class ProviderUnavailable(ProviderError):
    pass


class TokenBucket:
    def __init__(self, rate: float, burst: int = 1):
        self.rate = max(rate, 0.01)
        self.capacity = float(max(burst, 1))
        self.tokens = self.capacity
        self.updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                self.tokens = min(
                    self.capacity, self.tokens + (now - self.updated) * self.rate
                )
                self.updated = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
                await asyncio.sleep((1 - self.tokens) / self.rate)


_BUCKETS: dict[str, TokenBucket] = {}


def bucket_for(name: str, rate: float, burst: int = 1) -> TokenBucket:
    if name not in _BUCKETS:
        _BUCKETS[name] = TokenBucket(rate, burst)
    return _BUCKETS[name]


class ProviderContext:
    def __init__(
        self,
        session: Session,
        client: httpx.AsyncClient,
        store: SettingsStore,
    ):
        self.session = session
        self.client = client
        self.store = store


class Provider(ABC):
    name: str
    capabilities: set[Capability]
    rate: float = 1.0
    burst: int = 1

    def __init__(self, ctx: ProviderContext):
        self.ctx = ctx
        self.bucket = bucket_for(self.name, self.rate, self.burst)

    async def is_enabled(self) -> bool:
        return True

    async def search_release(self, query: ReleaseQuery) -> list[CanonicalRelease]:
        return []

    async def get_release(self, provider_id: str) -> CanonicalRelease | None:
        return None

    async def get_covers(self, release: CanonicalRelease) -> list[CoverCandidate]:
        return []

    def _cache_key(self, *parts: str) -> str:
        raw = "|".join([self.name, *parts])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def cached(
    session: Session,
    provider: str,
    key: str,
    ttl_seconds: int,
    loader: Callable[[], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    row = session.get(ProviderCache, key)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if row is not None:
        expires = row.expires_at
        if expires.tzinfo is not None:
            expires = expires.replace(tzinfo=None)
        if expires > now:
            return row.payload_json

    payload = await loader()
    expires_at = now + timedelta(seconds=ttl_seconds)
    if row is None:
        row = ProviderCache(
            key=key, provider=provider, payload_json=payload, expires_at=expires_at
        )
        session.add(row)
    else:
        row.payload_json = payload
        row.expires_at = expires_at
    session.commit()
    return payload

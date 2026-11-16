from __future__ import annotations

import asyncio
import time
from typing import Any

from .base import (
    CanonicalRelease,
    CanonicalTrack,
    Capability,
    CoverCandidate,
    Provider,
    ProviderError,
    ReleaseQuery,
    cached,
)

_TOKEN_CACHE: dict[str, tuple[str, float]] = {}


class SpotifyProvider(Provider):
    name = "spotify"
    capabilities = {Capability.SEARCH_RELEASE, Capability.GET_RELEASE, Capability.COVER}
    rate = 5.0
    burst = 5

    @property
    def client_id(self) -> str:
        return str(self.ctx.store.get("spotify.client_id") or "")

    @property
    def client_secret(self) -> str:
        return str(self.ctx.store.get("spotify.client_secret") or "")

    async def is_enabled(self) -> bool:
        return bool(self.client_id and self.client_secret)

    async def _token(self) -> str:
        cache_key = f"{self.client_id}:{self.client_secret[:8]}"
        cached_token = _TOKEN_CACHE.get(cache_key)
        if cached_token and cached_token[1] > time.monotonic() + 30:
            return cached_token[0]
        response = await self.ctx.client.post(
            "https://accounts.spotify.com/api/token",
            data={"grant_type": "client_credentials"},
            auth=(self.client_id, self.client_secret),
        )
        if response.status_code != 200:
            raise ProviderError(f"Spotify token HTTP {response.status_code}")
        data = response.json()
        token = data["access_token"]
        _TOKEN_CACHE[cache_key] = (token, time.monotonic() + int(data.get("expires_in", 3600)))
        return token

    async def _get(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        token = await self._token()
        for attempt in range(2):
            await self.bucket.acquire()
            response = await self.ctx.client.get(
                url, params=params, headers={"Authorization": f"Bearer {token}"}
            )
            if response.status_code == 429 and attempt == 0:
                retry_after = float(response.headers.get("Retry-After", "2"))
                await asyncio.sleep(min(retry_after, 10))
                continue
            if response.status_code != 200:
                raise ProviderError(f"Spotify HTTP {response.status_code}")
            return response.json()
        raise ProviderError("Spotify rate limited")

    async def search_release(self, query: ReleaseQuery) -> list[CanonicalRelease]:
        if not await self.is_enabled() or not query.album:
            return []
        text = f'album:"{query.album}"'
        if query.artist:
            text += f' artist:"{query.artist}"'
        key = self._cache_key("search", text)
        payload = await cached(
            self.ctx.session,
            self.name,
            key,
            7 * 24 * 3600,
            lambda: self._search(text),
        )
        albums = (payload.get("albums") or {}).get("items", [])[:5]
        releases: list[CanonicalRelease] = []
        for album in albums:
            album_id = album.get("id")
            if not album_id:
                continue
            try:
                detail = await cached(
                    self.ctx.session,
                    self.name,
                    self._cache_key("album", album_id),
                    30 * 24 * 3600,
                    lambda aid=album_id: self._get(f"https://api.spotify.com/v1/albums/{aid}"),
                )
            except ProviderError:
                continue
            parsed = self._parse(detail)
            if parsed:
                releases.append(parsed)
        return releases

    async def _search(self, text: str) -> dict[str, Any]:
        return await self._get(
            "https://api.spotify.com/v1/search",
            params={"q": text, "type": "album", "limit": 10},
        )

    async def get_release(self, provider_id: str) -> CanonicalRelease | None:
        payload = await cached(
            self.ctx.session,
            self.name,
            self._cache_key("album", provider_id),
            30 * 24 * 3600,
            lambda: self._get(f"https://api.spotify.com/v1/albums/{provider_id}"),
        )
        return self._parse(payload)

    def _parse(self, item: dict[str, Any]) -> CanonicalRelease | None:
        album_id = item.get("id")
        title = item.get("name")
        if not album_id or not title:
            return None
        tracks: list[CanonicalTrack] = []
        items = (item.get("tracks") or {}).get("items", [])
        for index, track in enumerate(items, start=1):
            artists = [artist.get("name", "") for artist in track.get("artists") or []]
            tracks.append(
                CanonicalTrack(
                    position=int(track.get("track_number") or index),
                    disc=int(track.get("disc_number") or 1),
                    title=track.get("name") or "Untitled",
                    artist=", ".join(name for name in artists if name) or None,
                    duration_ms=track.get("duration_ms"),
                )
            )
        covers: list[CoverCandidate] = []
        for image in item.get("images", []) or []:
            url = image.get("url")
            if url:
                covers.append(
                    CoverCandidate(
                        provider=self.name,
                        url=url,
                        width=image.get("width"),
                        height=image.get("height"),
                    )
                )
        release_date = item.get("release_date") or ""
        year = int(release_date[:4]) if release_date[:4].isdigit() else None
        artists = [artist.get("name", "") for artist in item.get("artists") or []]
        return CanonicalRelease(
            provider=self.name,
            provider_id=album_id,
            title=title,
            artist=", ".join(name for name in artists if name) or None,
            year=year,
            label=item.get("label"),
            barcode=(item.get("external_ids") or {}).get("upc"),
            genres=list(item.get("genres") or []),
            release_group_mbid=None,
            tracks=tracks,
            covers=covers,
        )

    async def get_covers(self, release: CanonicalRelease) -> list[CoverCandidate]:
        if release.covers:
            return release.covers
        fetched = await self.get_release(release.provider_id)
        return fetched.covers if fetched else []

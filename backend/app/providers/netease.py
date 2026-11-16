from __future__ import annotations

from typing import Any

from ..core.config import get_settings
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

NETEASE_HEADERS = {
    "Referer": "https://music.163.com/",
    "User-Agent": "Mozilla/5.0 (compatible; music-scrap/0.1)",
}


class NeteaseProvider(Provider):
    name = "netease"
    capabilities = {Capability.SEARCH_RELEASE, Capability.GET_RELEASE, Capability.COVER}
    rate = 0.5

    async def is_enabled(self) -> bool:
        if not get_settings().enable_unofficial_providers:
            return False
        return bool(self.ctx.store.get("netease.enabled"))

    async def search_release(self, query: ReleaseQuery) -> list[CanonicalRelease]:
        if not await self.is_enabled():
            return []
        text = " ".join(part for part in [query.artist, query.album] if part).strip()
        if not text:
            return []
        try:
            payload = await cached(
                self.ctx.session,
                self.name,
                self._cache_key("search", text),
                3 * 24 * 3600,
                lambda: self._search(text),
            )
        except ProviderError:
            return []
        albums = ((payload.get("result") or {}).get("albums")) or []
        releases: list[CanonicalRelease] = []
        for album in albums[:3]:
            album_id = album.get("id")
            if not album_id:
                continue
            try:
                detail = await cached(
                    self.ctx.session,
                    self.name,
                    self._cache_key("album", str(album_id)),
                    3 * 24 * 3600,
                    lambda aid=album_id: self._fetch_album(aid),
                )
            except ProviderError:
                continue
            parsed = self._parse(detail)
            if parsed:
                releases.append(parsed)
        return releases

    async def _search(self, text: str) -> dict[str, Any]:
        await self.bucket.acquire()
        response = await self.ctx.client.get(
            "https://music.163.com/api/search/get/web",
            params={"s": text, "type": 10, "limit": 10},
            headers=NETEASE_HEADERS,
        )
        if response.status_code != 200:
            raise ProviderError(f"NetEase HTTP {response.status_code}")
        return response.json()

    async def _fetch_album(self, album_id: str | int) -> dict[str, Any]:
        await self.bucket.acquire()
        response = await self.ctx.client.get(
            f"https://music.163.com/api/album/{album_id}",
            headers=NETEASE_HEADERS,
        )
        if response.status_code != 200:
            raise ProviderError(f"NetEase HTTP {response.status_code}")
        return response.json()

    async def get_release(self, provider_id: str) -> CanonicalRelease | None:
        try:
            payload = await cached(
                self.ctx.session,
                self.name,
                self._cache_key("album", provider_id),
                3 * 24 * 3600,
                lambda: self._fetch_album(provider_id),
            )
        except ProviderError:
            return None
        return self._parse(payload)

    def _parse(self, payload: dict[str, Any]) -> CanonicalRelease | None:
        album = payload.get("album") or payload.get("result")
        if not album:
            return None
        album_id = album.get("id")
        title = album.get("name")
        if not album_id or not title:
            return None
        tracks: list[CanonicalTrack] = []
        songs = album.get("songs") or album.get("tracks") or []
        for index, song in enumerate(songs, start=1):
            artists = [artist.get("name", "") for artist in song.get("ar") or []]
            duration = song.get("dt") or song.get("duration")
            tracks.append(
                CanonicalTrack(
                    position=int(song.get("no") or index),
                    disc=1,
                    title=song.get("name") or "Untitled",
                    artist=", ".join(name for name in artists if name) or None,
                    duration_ms=int(duration) if duration else None,
                )
            )
        covers: list[CoverCandidate] = []
        pic = album.get("picUrl") or (album.get("artist") or {}).get("picUrl")
        if pic:
            covers.append(CoverCandidate(provider=self.name, url=pic))
        artist = album.get("artist") or {}
        publish = album.get("publishTime") or 0
        year = None
        if publish:
            year = int(str(publish)[:4]) if len(str(publish)) >= 4 else None
        return CanonicalRelease(
            provider=self.name,
            provider_id=str(album_id),
            title=title,
            artist=artist.get("name"),
            year=year,
            genres=list(album.get("tags") or []),
            tracks=tracks,
            covers=covers,
        )

    async def get_covers(self, release: CanonicalRelease) -> list[CoverCandidate]:
        return release.covers

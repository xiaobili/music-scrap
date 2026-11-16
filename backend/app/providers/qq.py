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

QQ_HEADERS = {
    "Referer": "https://y.qq.com/",
    "User-Agent": "Mozilla/5.0 (compatible; music-scrap/0.1)",
}

SEARCH_URL = "https://c.y.qq.com/soso/fcgi-bin/client_search_cp"
ALBUM_URL = "https://c.y.qq.com/v8/fcg-bin/fcg_v8_album_info_cp.fcg"
COVER_URL = "https://y.gtimg.cn/music/photo_new/T002R500x500M000{mid}.jpg"


class QQProvider(Provider):
    name = "qq"
    capabilities = {Capability.SEARCH_RELEASE, Capability.GET_RELEASE, Capability.COVER}
    rate = 0.5

    async def is_enabled(self) -> bool:
        if not get_settings().enable_unofficial_providers:
            return False
        return bool(self.ctx.store.get("qq.enabled"))

    def _headers(self) -> dict[str, str]:
        headers = dict(QQ_HEADERS)
        cookie = str(self.ctx.store.get("qq.cookie") or "").strip()
        if cookie:
            headers["Cookie"] = cookie
        return headers

    @staticmethod
    def _album_mids(payload: dict[str, Any]) -> list[str]:
        songs = ((payload.get("data") or {}).get("song") or {}).get("list") or []
        mids: list[str] = []
        for song in songs:
            mid = (song.get("album") or {}).get("mid") or song.get("albummid")
            if mid and mid not in mids:
                mids.append(str(mid))
        return mids[:3]

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
        releases: list[CanonicalRelease] = []
        for mid in self._album_mids(payload):
            try:
                detail = await cached(
                    self.ctx.session,
                    self.name,
                    self._cache_key("album", mid),
                    3 * 24 * 3600,
                    lambda album_mid=mid: self._fetch_album(album_mid),
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
            SEARCH_URL,
            params={
                "w": text,
                "p": 1,
                "n": 10,
                "t": 0,
                "format": "json",
                "new_json": 1,
                "cr": 1,
                "catZhida": 1,
                "needNewCode": 0,
            },
            headers=self._headers(),
        )
        if response.status_code != 200:
            raise ProviderError(f"QQ Music HTTP {response.status_code}")
        return response.json()

    async def _fetch_album(self, album_mid: str) -> dict[str, Any]:
        await self.bucket.acquire()
        response = await self.ctx.client.get(
            ALBUM_URL,
            params={
                "albummid": album_mid,
                "g_tk": 5381,
                "format": "json",
                "platform": "yqq",
                "needNewCode": 0,
                "new_format": 1,
            },
            headers=self._headers(),
        )
        if response.status_code != 200:
            raise ProviderError(f"QQ Music HTTP {response.status_code}")
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
        data = payload.get("data") or {}
        album_mid = data.get("mid") or data.get("albummid")
        title = data.get("name") or data.get("albumname")
        if not album_mid or not title:
            return None
        tracks: list[CanonicalTrack] = []
        for index, song in enumerate(data.get("list") or [], start=1):
            cd_index = song.get("cdIdx")
            position = int(cd_index) + 1 if cd_index is not None else index
            artists = [artist.get("name", "") for artist in song.get("singer") or []]
            duration = song.get("interval")
            tracks.append(
                CanonicalTrack(
                    position=position,
                    disc=int(song.get("belongCD") or 1),
                    title=song.get("songname") or "Untitled",
                    artist=", ".join(name for name in artists if name) or None,
                    duration_ms=int(duration) * 1000 if duration else None,
                )
            )
        year = None
        release_date = str(data.get("aDate") or "")
        if release_date[:4].isdigit():
            year = int(release_date[:4])
        genres = [str(data["genre"])] if data.get("genre") else []
        covers = [
            CoverCandidate(provider=self.name, url=COVER_URL.format(mid=album_mid))
        ]
        return CanonicalRelease(
            provider=self.name,
            provider_id=str(album_mid),
            title=title,
            artist=data.get("singername"),
            year=year,
            label=data.get("company"),
            genres=genres,
            tracks=tracks,
            covers=covers,
        )

    async def get_covers(self, release: CanonicalRelease) -> list[CoverCandidate]:
        return release.covers

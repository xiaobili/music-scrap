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


def _duration_ms(value: str | None) -> int | None:
    if not value:
        return None
    parts = value.split(":")
    try:
        numbers = [int(part) for part in parts]
    except ValueError:
        return None
    seconds = 0
    for number in numbers:
        seconds = seconds * 60 + number
    return seconds * 1000


class DiscogsProvider(Provider):
    name = "discogs"
    capabilities = {Capability.SEARCH_RELEASE, Capability.GET_RELEASE, Capability.COVER}
    rate = 1.0

    @property
    def token(self) -> str:
        return str(self.ctx.store.get("discogs.token") or "")

    async def is_enabled(self) -> bool:
        if not self.ctx.store.get("discogs.enabled", True):
            return False
        return bool(self.token)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Discogs token={self.token}",
            "User-Agent": get_settings().musicbrainz_user_agent,
        }

    async def search_release(self, query: ReleaseQuery) -> list[CanonicalRelease]:
        if not await self.is_enabled():
            return []
        text = " ".join(part for part in [query.artist, query.album] if part).strip()
        if not text:
            return []
        key = self._cache_key("search", text)
        payload = await cached(
            self.ctx.session,
            self.name,
            key,
            7 * 24 * 3600,
            lambda: self._search(text),
        )
        results = payload.get("results", [])[:5]
        releases: list[CanonicalRelease] = []
        for item in results:
            release_id = str(item.get("id") or "")
            if not release_id:
                continue
            detail_key = self._cache_key("release", release_id)
            try:
                detail = await cached(
                    self.ctx.session,
                    self.name,
                    detail_key,
                    30 * 24 * 3600,
                    lambda rid=release_id: self._fetch(rid),
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
            "https://api.discogs.com/database/search",
            params={"q": text, "type": "release", "per_page": 10},
            headers=self._headers(),
        )
        if response.status_code != 200:
            raise ProviderError(f"Discogs HTTP {response.status_code}")
        return response.json()

    async def _fetch(self, release_id: str) -> dict[str, Any]:
        await self.bucket.acquire()
        response = await self.ctx.client.get(
            f"https://api.discogs.com/releases/{release_id}",
            headers=self._headers(),
        )
        if response.status_code != 200:
            raise ProviderError(f"Discogs HTTP {response.status_code}")
        return response.json()

    async def get_release(self, provider_id: str) -> CanonicalRelease | None:
        payload = await cached(
            self.ctx.session,
            self.name,
            self._cache_key("release", provider_id),
            30 * 24 * 3600,
            lambda: self._fetch(provider_id),
        )
        return self._parse(payload)

    def _parse(self, item: dict[str, Any]) -> CanonicalRelease | None:
        release_id = str(item.get("id") or "")
        title = item.get("title")
        if not release_id or not title:
            return None

        tracks: list[CanonicalTrack] = []
        index = 0
        for track in item.get("tracklist", []) or []:
            if track.get("type_") not in (None, "track"):
                continue
            index += 1
            position = str(track.get("position") or index)
            number = position.split("-")[-1]
            try:
                position_number = int("".join(ch for ch in number if ch.isdigit()) or index)
            except ValueError:
                position_number = index
            track_artists = [
                artist.get("name", "") for artist in (track.get("artists") or [])
            ]
            tracks.append(
                CanonicalTrack(
                    position=position_number,
                    disc=1,
                    title=track.get("title") or "Untitled",
                    artist=", ".join(name for name in track_artists if name) or None,
                    duration_ms=_duration_ms(track.get("duration")),
                )
            )

        artists = item.get("artists") or []
        labels = item.get("labels") or []
        barcode = None
        for identifier in item.get("identifiers", []) or []:
            if str(identifier.get("type", "")).lower() == "barcode":
                barcode = identifier.get("value")
                break

        covers: list[CoverCandidate] = []
        for image in item.get("images", []) or []:
            url = image.get("uri") or image.get("uri150")
            if url:
                covers.append(
                    CoverCandidate(
                        provider=self.name,
                        url=url,
                        width=image.get("width"),
                        height=image.get("height"),
                    )
                )

        return CanonicalRelease(
            provider=self.name,
            provider_id=release_id,
            title=title,
            artist=", ".join(a.get("name", "") for a in artists) or None,
            year=item.get("year"),
            label=labels[0].get("name") if labels else None,
            catalog_number=labels[0].get("catno") if labels else None,
            barcode=barcode,
            genres=list(item.get("genres") or []) + list(item.get("styles") or []),
            country=item.get("country"),
            format=", ".join(f.get("name", "") for f in item.get("formats", []) or []),
            tracks=tracks,
            covers=covers,
        )

    async def get_covers(self, release: CanonicalRelease) -> list[CoverCandidate]:
        if release.covers:
            return release.covers
        fetched = await self.get_release(release.provider_id)
        return fetched.covers if fetched else []

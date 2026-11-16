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
    bucket_for,
    cached,
)


def _artist_credit(credits: list[dict[str, Any]] | None) -> str | None:
    if not credits:
        return None
    parts: list[str] = []
    for credit in credits:
        name = credit.get("name") or (credit.get("artist") or {}).get("name") or ""
        parts.append(f"{name}{credit.get('joinphrase') or ''}")
    value = "".join(parts).strip()
    return value or None


def _year(date_value: str | None) -> int | None:
    if date_value and len(date_value) >= 4 and date_value[:4].isdigit():
        return int(date_value[:4])
    return None


class MusicBrainzProvider(Provider):
    name = "musicbrainz"
    capabilities = {
        Capability.SEARCH_RELEASE,
        Capability.GET_RELEASE,
        Capability.COVER,
    }
    rate = 1.0

    @property
    def user_agent(self) -> str:
        return get_settings().musicbrainz_user_agent

    async def is_enabled(self) -> bool:
        return bool(self.ctx.store.get("musicbrainz.enabled", True))

    async def search_release(self, query: ReleaseQuery) -> list[CanonicalRelease]:
        parts: list[str] = []
        if query.album:
            parts.append(f'release:"{query.album}"')
        if query.artist:
            parts.append(f'artist:"{query.artist}"')
        if query.year and query.year_to and query.year != query.year_to:
            parts.append(f"date:[{query.year} TO {query.year_to}]")
        elif query.year:
            parts.append(f"date:{query.year}")
        text = " AND ".join(parts) or query.album or ""
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
        releases = []
        for item in payload.get("releases", [])[:5]:
            release_id = item.get("id")
            if not release_id:
                continue
            try:
                detailed = await cached(
                    self.ctx.session,
                    self.name,
                    self._cache_key("release", release_id),
                    30 * 24 * 3600,
                    lambda rid=release_id: self._fetch_release(rid),
                )
                parsed = self._parse_release(detailed)
            except ProviderError:
                parsed = self._parse_release(item)
            if parsed:
                releases.append(parsed)
        return releases

    async def _search(self, text: str) -> dict[str, Any]:
        await self.bucket.acquire()
        response = await self.ctx.client.get(
            "https://musicbrainz.org/ws/2/release/",
            params={
                "query": text,
                "fmt": "json",
                "limit": 10,
                "inc": "recordings artist-credits labels release-groups",
            },
            headers={"User-Agent": self.user_agent},
        )
        if response.status_code != 200:
            raise ProviderError(f"MusicBrainz HTTP {response.status_code}")
        return response.json()

    async def get_release(self, provider_id: str) -> CanonicalRelease | None:
        key = self._cache_key("release", provider_id)
        payload = await cached(
            self.ctx.session,
            self.name,
            key,
            30 * 24 * 3600,
            lambda: self._fetch_release(provider_id),
        )
        return self._parse_release(payload)

    async def _fetch_release(self, provider_id: str) -> dict[str, Any]:
        await self.bucket.acquire()
        response = await self.ctx.client.get(
            f"https://musicbrainz.org/ws/2/release/{provider_id}",
            params={
                "fmt": "json",
                "inc": "recordings artist-credits labels release-groups",
            },
            headers={"User-Agent": self.user_agent},
        )
        if response.status_code != 200:
            raise ProviderError(f"MusicBrainz HTTP {response.status_code}")
        return response.json()

    def _parse_release(self, item: dict[str, Any]) -> CanonicalRelease | None:
        release_id = item.get("id")
        title = item.get("title")
        if not release_id or not title:
            return None

        tracks: list[CanonicalTrack] = []
        for medium in item.get("media", []) or []:
            disc = int(medium.get("position") or 1)
            for index, track in enumerate(medium.get("tracks", []) or [], start=1):
                recording = track.get("recording") or {}
                number = track.get("number") or str(index)
                try:
                    position = int(str(number).split("/")[0])
                except ValueError:
                    position = index
                isrcs = recording.get("isrcs") or []
                tracks.append(
                    CanonicalTrack(
                        position=position,
                        disc=disc,
                        title=recording.get("title") or track.get("title") or "Untitled",
                        artist=_artist_credit(recording.get("artist-credit")),
                        duration_ms=track.get("length") or recording.get("length"),
                        isrc=isrcs[0] if isrcs else None,
                        mbid=recording.get("id"),
                    )
                )

        label_info = item.get("label-info") or []
        label = None
        catalog_number = None
        if label_info:
            label = (label_info[0].get("label") or {}).get("name")
            catalog_number = label_info[0].get("catalog-number")

        return CanonicalRelease(
            provider=self.name,
            provider_id=release_id,
            title=title,
            artist=_artist_credit(item.get("artist-credit")),
            year=_year(item.get("date")),
            label=label,
            catalog_number=catalog_number,
            barcode=item.get("barcode"),
            genres=[],
            country=item.get("country"),
            release_mbid=release_id,
            release_group_mbid=(item.get("release-group") or {}).get("id"),
            tracks=tracks,
        )

    async def get_covers(self, release: CanonicalRelease) -> list[CoverCandidate]:
        mbid = release.release_mbid or release.provider_id
        bucket = bucket_for("coverartarchive", 1.0)
        await bucket.acquire()
        try:
            response = await self.ctx.client.get(
                f"https://coverartarchive.org/release/{mbid}",
                headers={"User-Agent": self.user_agent},
                follow_redirects=True,
            )
        except Exception:
            return []
        if response.status_code != 200:
            return []
        images = response.json().get("images", [])
        covers: list[CoverCandidate] = []
        for image in images:
            types = image.get("types") or []
            if not image.get("front") and "Front" not in types:
                continue
            url = image.get("image") or (image.get("thumbnails") or {}).get("large")
            if url:
                covers.append(
                    CoverCandidate(provider=self.name, url=url.replace("http://", "https://"))
                )
        return covers

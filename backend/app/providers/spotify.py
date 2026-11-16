from __future__ import annotations

from typing import Any

from spotapi import Public, SpotAPIError, to_dict

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


def _album_id(uri: str | None) -> str | None:
    if not uri:
        return None
    return uri.rsplit(":", 1)[-1] or None


def _artist_names(artists: dict[str, Any] | None) -> list[str]:
    items = (artists or {}).get("items") or []
    names = [(item.get("profile") or {}).get("name") for item in items]
    return [name for name in names if name]


class SpotifyProvider(Provider):
    name = "spotify"
    capabilities = {Capability.SEARCH_RELEASE, Capability.GET_RELEASE, Capability.COVER}
    rate = 2.0

    async def is_enabled(self) -> bool:
        return bool(self.ctx.store.get("spotify.enabled", True))

    async def search_release(self, query: ReleaseQuery) -> list[CanonicalRelease]:
        if not await self.is_enabled() or not query.album:
            return []
        text = f'album:"{query.album}"'
        if query.artist:
            text += f' artist:"{query.artist}"'
        payload = await cached(
            self.ctx.session,
            self.name,
            self._cache_key("search", text),
            7 * 24 * 3600,
            lambda: self._search(text),
        )
        releases: list[CanonicalRelease] = []
        for album in (payload.get("albums") or [])[:5]:
            album_id = _album_id(album.get("uri"))
            if not album_id:
                continue
            try:
                detail = await self._album(album_id)
            except ProviderError:
                continue
            parsed = self._parse(detail)
            if parsed:
                releases.append(parsed)
        return releases

    async def _search(self, text: str) -> dict[str, Any]:
        await self.bucket.acquire()
        try:
            results = await Public.search(text, types="album", limit=10)
        except SpotAPIError as exc:
            raise ProviderError(f"Spotify search failed: {exc}") from exc
        return to_dict(results)

    async def _album(self, album_id: str) -> dict[str, Any]:
        return await cached(
            self.ctx.session,
            self.name,
            self._cache_key("album", album_id),
            30 * 24 * 3600,
            lambda: self._fetch_album(album_id),
        )

    async def _fetch_album(self, album_id: str) -> dict[str, Any]:
        await self.bucket.acquire()
        try:
            detail = await Public.get_album(album_id)
        except SpotAPIError as exc:
            raise ProviderError(f"Spotify album failed: {exc}") from exc
        return to_dict(detail)

    async def get_release(self, provider_id: str) -> CanonicalRelease | None:
        payload = await self._album(provider_id)
        return self._parse(payload)

    def _parse(self, item: dict[str, Any]) -> CanonicalRelease | None:
        album_id = _album_id(item.get("uri"))
        title = item.get("name")
        if not album_id or not title:
            return None
        tracks: list[CanonicalTrack] = []
        entries = ((item.get("tracks_v2") or {}).get("items")) or []
        for index, entry in enumerate(entries, start=1):
            track = entry.get("track") or {}
            duration = (track.get("duration") or {}).get("total_milliseconds")
            tracks.append(
                CanonicalTrack(
                    position=int(track.get("track_number") or index),
                    disc=int(track.get("disc_number") or 1),
                    title=track.get("name") or "Untitled",
                    artist=", ".join(_artist_names(track.get("artists"))) or None,
                    duration_ms=int(duration) if duration is not None else None,
                )
            )
        covers: list[CoverCandidate] = []
        for source in ((item.get("cover_art") or {}).get("sources")) or []:
            url = source.get("url")
            if url:
                covers.append(
                    CoverCandidate(
                        provider=self.name,
                        url=url,
                        width=source.get("width"),
                        height=source.get("height"),
                    )
                )
        release_date = (item.get("date") or {}).get("iso_string") or ""
        year = int(release_date[:4]) if release_date[:4].isdigit() else None
        return CanonicalRelease(
            provider=self.name,
            provider_id=album_id,
            title=title,
            artist=", ".join(_artist_names(item.get("artists"))) or None,
            year=year,
            label=item.get("label"),
            barcode=None,
            genres=[],
            release_group_mbid=None,
            tracks=tracks,
            covers=covers,
        )

    async def get_covers(self, release: CanonicalRelease) -> list[CoverCandidate]:
        if release.covers:
            return release.covers
        fetched = await self.get_release(release.provider_id)
        return fetched.covers if fetched else []

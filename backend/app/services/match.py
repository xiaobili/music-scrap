from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx
from rapidfuzz import fuzz
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..db.models import Album, ChangePlan, MatchCandidate, Track
from ..providers.acoustid import AcoustIDProvider
from ..providers.base import (
    CanonicalRelease,
    Provider,
    ProviderContext,
    ProviderError,
    ReleaseQuery,
)
from ..providers.registry import ProviderRegistry
from ..services.settings import SettingsStore
from .text import field_variants, has_cjk, to_simplified

WEIGHTS = {
    "title": 0.35,
    "artist": 0.25,
    "track_count": 0.15,
    "duration": 0.15,
    "year": 0.10,
}


def similarity(left: str | None, right: str | None) -> float:
    if not left or not right:
        return 0.0
    a = left.strip().lower()
    b = right.strip().lower()
    if not a or not b:
        return 0.0
    if has_cjk(a + b):
        raw = fuzz.ratio(a, b) / 100.0
        normalized = fuzz.ratio(to_simplified(a), to_simplified(b)) / 100.0
        return max(raw, normalized)
    return fuzz.token_set_ratio(a, b) / 100.0


def _duration_ms(tracks: list[Track] | list[Any]) -> int:
    total = 0
    for track in tracks:
        value = getattr(track, "duration_ms", None)
        if value is None and isinstance(track, dict):
            value = track.get("duration_ms")
        total += int(value or 0)
    return total


def score_release(
    release: CanonicalRelease,
    album_title: str | None,
    album_artist: str | None,
    year: int | None,
    local_tracks: list[Track],
    acoustid_groups: set[str] | None = None,
    year_range: tuple[int, int] | None = None,
) -> tuple[float, dict[str, Any]]:
    title_score = similarity(album_title, release.title)
    artist_score = similarity(album_artist, release.artist)

    local_count = len(local_tracks)
    remote_count = len(release.tracks)
    if local_count and remote_count:
        count_score = max(0.0, 1.0 - abs(local_count - remote_count) / max(local_count, remote_count))
    else:
        count_score = 0.0

    local_duration = _duration_ms(local_tracks)
    remote_duration = _duration_ms(release.tracks)
    if local_duration and remote_duration:
        diff = abs(local_duration - remote_duration)
        duration_score = max(0.0, 1.0 - diff / max(local_duration, 300_000))
    else:
        duration_score = 0.5

    if year_range is not None:
        low, high = year_range
        year_score = (
            1.0 if release.year is not None and low <= release.year <= high else 0.0
        )
    elif year and release.year:
        delta = abs(year - release.year)
        year_score = 1.0 if delta == 0 else (0.5 if delta <= 1 else 0.0)
    else:
        year_score = 0.5

    parts = {
        "title": {"weight": WEIGHTS["title"], "value": round(title_score, 4)},
        "artist": {"weight": WEIGHTS["artist"], "value": round(artist_score, 4)},
        "track_count": {"weight": WEIGHTS["track_count"], "value": round(count_score, 4)},
        "duration": {"weight": WEIGHTS["duration"], "value": round(duration_score, 4)},
        "year": {"weight": WEIGHTS["year"], "value": round(year_score, 4)},
    }
    score = sum(item["weight"] * item["value"] for item in parts.values())

    if acoustid_groups and release.release_group_mbid in acoustid_groups:
        parts["acoustid_bonus"] = {"weight": 0.10, "value": 1.0}
        score += 0.10

    parts["final"] = round(min(score, 1.0), 4)
    return min(score, 1.0), parts


def _query_from_album(album: Album) -> ReleaseQuery:
    return ReleaseQuery(
        album=album.album,
        artist=album.artist,
        year=album.year,
        track_count=album.track_count,
        mbid=album.mbid,
    )


def _query_variants(query: ReleaseQuery) -> list[ReleaseQuery]:
    return [
        query.model_copy(update={"album": album, "artist": artist})
        for album, artist in field_variants(query.album, query.artist)
    ]


async def _search_releases(
    providers: list[Provider], queries: list[ReleaseQuery]
) -> list[CanonicalRelease]:
    if not queries:
        return []
    results = await asyncio.gather(
        *[
            provider.search_release(query)
            for provider in providers
            for query in queries
        ],
        return_exceptions=True,
    )
    collected: list[CanonicalRelease] = []
    for result in results:
        if isinstance(result, Exception):
            continue
        collected.extend(result)
    return collected


async def _acoustid_groups(
    session: Session, client: httpx.AsyncClient, tracks: list[Track]
) -> set[str]:
    ctx = ProviderContext(session, client, SettingsStore(session))
    provider = AcoustIDProvider(ctx)
    if not await provider.is_enabled():
        return set()
    groups: set[str] = set()
    for track in tracks[:3]:
        groups.update(await provider.lookup_release_groups(track.path))
    return groups


async def match_album(
    session: Session,
    album_id: int,
    client: httpx.AsyncClient,
    *,
    search: ReleaseQuery | None = None,
) -> list[MatchCandidate]:
    album = session.get(Album, album_id)
    if album is None:
        raise ValueError("album not found")
    tracks = list(
        session.scalars(
            select(Track).where(Track.album_id == album.id).order_by(Track.disc_no, Track.track_no)
        ).all()
    )

    registry = ProviderRegistry(ProviderContext(session, client, SettingsStore(session)))
    active = await registry.enabled()
    if not active:
        return []

    query = search or _query_from_album(album)

    groups: set[str] = set()
    if album.kind == "split":
        groups = await _acoustid_groups(session, client, tracks)

    searchable = [provider for provider in active if provider.name != "acoustid"]
    queries = _query_variants(query)
    # 外部曲库对台版/港版发行常收录繁体标题。手动检索同时覆盖简繁变体；
    # 自动匹配仅在原始查询零结果时回退变体，避免批量匹配请求量翻倍。
    if search is None:
        primary, fallback = queries[:1], queries[1:]
    else:
        primary, fallback = queries, []
    collected = await _search_releases(searchable, primary)
    if not collected and fallback:
        collected = await _search_releases(searchable, fallback)

    deduped: dict[tuple[str, str], CanonicalRelease] = {}
    for release in collected:
        deduped[(release.provider, release.provider_id)] = release

    year_range: tuple[int, int] | None = None
    if search is not None and (search.year is not None or search.year_to is not None):
        year_range = (search.year or 0, search.year_to or 9999)
        deduped = {
            key: release
            for key, release in deduped.items()
            if release.year is not None
            and year_range[0] <= release.year <= year_range[1]
        }

    score_title = query.album or album.album
    score_artist = query.artist or album.artist
    score_year = None if year_range is not None else (query.year or album.year)

    scored: list[tuple[float, dict[str, Any], CanonicalRelease]] = []
    for release in deduped.values():
        score, parts = score_release(
            release,
            score_title,
            score_artist,
            score_year,
            tracks,
            groups,
            year_range=year_range,
        )
        scored.append((score, parts, release))
    scored.sort(key=lambda item: item[0], reverse=True)

    session.execute(delete(MatchCandidate).where(MatchCandidate.album_id == album.id))
    rows: list[MatchCandidate] = []
    for score, parts, release in scored:
        row = MatchCandidate(
            album_id=album.id,
            provider=release.provider,
            provider_id=release.provider_id,
            score=score,
            payload_json=release.model_dump(mode="json"),
            raw_score_json=parts,
            fetched_at=datetime.now(timezone.utc),
        )
        session.add(row)
        rows.append(row)

    best = scored[0][0] if scored else 0.0
    album.confidence = best
    # 已有人工选定的变更计划说明匹配已完成，自动重新检索不得把状态降级
    has_plan = (
        session.scalar(
            select(ChangePlan.id).where(ChangePlan.album_id == album.id).limit(1)
        )
        is not None
    )
    if has_plan or best >= 0.85:
        album.status = "matched"
    elif best >= 0.60:
        album.status = "pending"
    else:
        album.status = "unmatched"
    session.commit()
    for row in rows:
        session.refresh(row)
    return rows


async def get_cover_candidates(
    session: Session,
    album_id: int,
    candidate_id: int,
    client: httpx.AsyncClient,
) -> list[dict[str, Any]]:
    album = session.get(Album, album_id)
    candidate = session.get(MatchCandidate, candidate_id)
    if album is None or candidate is None:
        raise ValueError("album or candidate not found")
    release = CanonicalRelease.model_validate(candidate.payload_json)
    registry = ProviderRegistry(ProviderContext(session, client, SettingsStore(session)))
    provider = registry.get(release.provider)
    covers: list[dict[str, Any]] = []
    if provider is not None:
        try:
            items = await provider.get_covers(release)
        except ProviderError:
            items = []
        covers.extend(item.model_dump() for item in items)

    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for cover in covers:
        if cover["url"] in seen:
            continue
        seen.add(cover["url"])
        unique.append(cover)
    unique.sort(
        key=lambda cover: int(cover.get("width") or 0) * int(cover.get("height") or 0),
        reverse=True,
    )
    return unique

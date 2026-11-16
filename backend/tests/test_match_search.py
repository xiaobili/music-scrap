from __future__ import annotations

import asyncio

import httpx
import pytest

from app.db.models import Album, LibraryRoot, ProviderCache, Track
from app.providers.base import CanonicalRelease, CanonicalTrack, ReleaseQuery, cached
from app.services import match as match_service
from app.services.match import match_album
from app.services.text import field_variants, to_simplified, to_traditional


def test_to_traditional_and_back():
    assert to_traditional("叶惠美") == "葉惠美"
    assert to_simplified("葉惠美") == "叶惠美"


def test_field_variants_adds_traditional_for_simplified_input():
    assert field_variants("叶惠美", "周杰伦") == [
        ("叶惠美", "周杰伦"),
        ("葉惠美", "周杰倫"),
    ]


def test_field_variants_adds_simplified_for_traditional_input():
    assert field_variants("葉惠美", "周傑倫") == [
        ("葉惠美", "周傑倫"),
        ("叶惠美", "周杰伦"),
    ]


def test_field_variants_skips_non_chinese():
    assert field_variants("Random Access Memories", "Daft Punk") == [
        ("Random Access Memories", "Daft Punk")
    ]


def test_field_variants_handles_missing_fields():
    assert field_variants(None, "周杰伦") == [(None, "周杰伦"), (None, "周杰倫")]


class _ScriptAwareProvider:
    """只对指定专辑名的检索返回结果，模拟只收录繁体标题的外部曲库。"""

    name = "musicbrainz"

    def __init__(self, accepted_album: str):
        self.accepted_album = accepted_album
        self.queries: list[ReleaseQuery] = []

    async def is_enabled(self) -> bool:
        return True

    async def search_release(self, query: ReleaseQuery) -> list[CanonicalRelease]:
        self.queries.append(query)
        if query.album != self.accepted_album:
            return []
        return [
            CanonicalRelease(
                provider=self.name,
                provider_id="mb-1",
                title="葉惠美",
                artist="周傑倫",
                year=2003,
                tracks=[
                    CanonicalTrack(position=1, title="以父之名", duration_ms=321000),
                    CanonicalTrack(position=2, title="懦夫", duration_ms=201000),
                ],
            )
        ]

    async def get_covers(self, release: CanonicalRelease):
        return []


class _Registry:
    def __init__(self, provider):
        self.provider = provider

    async def enabled(self):
        return [self.provider]

    def get(self, name):
        return self.provider


def _use_provider(monkeypatch, provider) -> None:
    monkeypatch.setattr(match_service, "ProviderRegistry", lambda ctx: _Registry(provider))


def _make_album(db, *, album: str, artist: str) -> Album:
    root = LibraryRoot(path="/tmp/match-search-library")
    db.add(root)
    db.flush()
    row = Album(
        root_id=root.id,
        rel_path="周杰伦/叶惠美",
        kind="split",
        status="unmatched",
        artist=artist,
        album=album,
        year=2003,
        track_count=2,
    )
    db.add(row)
    db.flush()
    db.add_all(
        [
            Track(
                album_id=row.id,
                path=f"/tmp/match-{row.id}-1.flac",
                ext="flac",
                format="FLAC",
                track_no=1,
                duration_ms=321000,
            ),
            Track(
                album_id=row.id,
                path=f"/tmp/match-{row.id}-2.flac",
                ext="flac",
                format="FLAC",
                track_no=2,
                duration_ms=201000,
            ),
        ]
    )
    db.commit()
    return row


@pytest.mark.asyncio
async def test_cached_handles_concurrent_writes_for_same_key(db):
    async def loader():
        await asyncio.sleep(0.01)
        return {"releases": [{"id": "mb-1"}]}

    first, second = await asyncio.gather(
        cached(db, "musicbrainz", "shared-key", 60, loader),
        cached(db, "musicbrainz", "shared-key", 60, loader),
    )

    assert first == second == {"releases": [{"id": "mb-1"}]}
    stored = db.get(ProviderCache, "shared-key")
    assert stored is not None and stored.provider == "musicbrainz"


@pytest.mark.asyncio
async def test_manual_simplified_search_reaches_traditional_catalog(db, monkeypatch):
    provider = _ScriptAwareProvider(accepted_album="葉惠美")
    _use_provider(monkeypatch, provider)
    album = _make_album(db, album="叶惠美", artist="周杰伦")

    async with httpx.AsyncClient() as client:
        rows = await match_album(
            db,
            album.id,
            client,
            search=ReleaseQuery(album="叶惠美", artist="周杰伦"),
        )

    assert [row.provider_id for row in rows] == ["mb-1"]
    assert any(query.album == "葉惠美" for query in provider.queries)


@pytest.mark.asyncio
async def test_auto_match_retries_variant_when_original_empty(db, monkeypatch):
    provider = _ScriptAwareProvider(accepted_album="葉惠美")
    _use_provider(monkeypatch, provider)
    album = _make_album(db, album="叶惠美", artist="周杰伦")

    async with httpx.AsyncClient() as client:
        rows = await match_album(db, album.id, client)

    assert len(rows) == 1
    assert provider.queries[0].album == "叶惠美"
    assert provider.queries[-1].album == "葉惠美"


@pytest.mark.asyncio
async def test_auto_match_skips_variant_when_original_hits(db, monkeypatch):
    provider = _ScriptAwareProvider(accepted_album="叶惠美")
    _use_provider(monkeypatch, provider)
    album = _make_album(db, album="叶惠美", artist="周杰伦")

    async with httpx.AsyncClient() as client:
        await match_album(db, album.id, client)

    assert [query.album for query in provider.queries] == ["叶惠美"]

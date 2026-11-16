from __future__ import annotations

import asyncio
import time

import pytest

from app.db.models import Track
from app.providers.base import CanonicalRelease, CanonicalTrack, TokenBucket, cached
from app.services.match import score_release, similarity


def _release(**overrides) -> CanonicalRelease:
    payload = dict(
        provider="musicbrainz",
        provider_id="mb-1",
        title="城市天气",
        artist="甜梅号",
        year=2010,
        tracks=[
            CanonicalTrack(position=1, title="一个人的旅行", duration_ms=312000),
            CanonicalTrack(position=2, title="城市天气", duration_ms=278000),
        ],
    )
    payload.update(overrides)
    return CanonicalRelease(**payload)


def _tracks() -> list[Track]:
    return [
        Track(path="/tmp/a.flac", ext="flac", format="FLAC", track_no=1, title="一个人的旅行", duration_ms=312000),
        Track(path="/tmp/b.flac", ext="flac", format="FLAC", track_no=2, title="城市天气", duration_ms=278000),
    ]


def test_score_exact_match_above_085():
    score, parts = score_release(_release(), "城市天气", "甜梅号", 2010, _tracks())
    assert score >= 0.85
    assert parts["final"] == pytest.approx(score, abs=1e-4)


def test_weights_sum_to_one():
    _, parts = score_release(_release(), "城市天气", "甜梅号", 2010, _tracks())
    total = sum(item["weight"] for key, item in parts.items() if key in {"title", "artist", "track_count", "duration", "year"})
    assert total == pytest.approx(1.0)


def test_duration_penalty():
    tracks = _tracks()
    tracks[0].duration_ms = 2_000_000
    _, parts = score_release(_release(), "城市天气", "甜梅号", 2010, tracks)
    assert parts["duration"]["value"] < 0.6


def test_manual_similarity_for_chinese():
    assert similarity("城市天气", "城市天氣") > 0.5
    assert similarity(None, "x") == 0.0


def test_acoustid_bonus_raises_score():
    base, _ = score_release(_release(), "城市天气", "甜梅号", 2012, _tracks())
    boosted, parts = score_release(
        _release(release_group_mbid="rg-1"),
        "城市天气",
        "甜梅号",
        2012,
        _tracks(),
        {"rg-1"},
    )
    assert boosted > base
    assert "acoustid_bonus" in parts


@pytest.mark.asyncio
async def test_token_bucket_spacing():
    bucket = TokenBucket(rate=10, burst=1)
    start = time.monotonic()
    await bucket.acquire()
    await bucket.acquire()
    await bucket.acquire()
    assert time.monotonic() - start >= 0.18


@pytest.mark.asyncio
async def test_cache_hit_avoids_loader(db):
    calls = 0

    async def loader():
        nonlocal calls
        calls += 1
        return {"value": calls}

    first = await cached(db, "test", "key", 60, loader)
    second = await cached(db, "test", "key", 60, loader)
    assert first == second == {"value": 1}
    assert calls == 1

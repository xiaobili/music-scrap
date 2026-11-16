from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app import tagio
from app.db.models import Album, ChangePlan, LibraryRoot, MatchCandidate, Track
from app.providers.base import CanonicalRelease, CanonicalTrack, CoverCandidate
from app.services.plan import build_plan, patch_items

from .conftest import make_audio


def _release() -> CanonicalRelease:
    return CanonicalRelease(
        provider="musicbrainz",
        provider_id="mb-1",
        title="城市天气",
        artist="甜梅号",
        year=2010,
        label="小白兔唱片",
        catalog_number="RB-045",
        release_mbid="mb-1",
        tracks=[
            CanonicalTrack(position=1, title="一个人的旅行", duration_ms=3000),
            CanonicalTrack(position=2, title="城市天气", duration_ms=3000),
        ],
        covers=[CoverCandidate(provider="musicbrainz", url="https://example.com/cover.jpg")],
    )


def _setup(db, tmp_path: Path, *, kind: str = "split"):
    library = tmp_path / "library"
    directory = library / "甜梅号" / "城市天气 (2010)"
    directory.mkdir(parents=True)
    first = make_audio(directory / "01.flac")
    second = make_audio(directory / "02.flac")
    tagio.write(first, {"ALBUM": "城市天气", "TITLE": "旧标题", "TRACKNUMBER": "1"})
    tagio.write(second, {"ALBUM": "城市天气", "TRACKNUMBER": "2"})

    root = LibraryRoot(path=str(library))
    db.add(root)
    db.commit()

    album = Album(
        root_id=root.id,
        rel_path="甜梅号/城市天气 (2010)",
        kind=kind,
        status="pending",
        artist="甜梅号",
        album="城市天气",
        year=2010,
        track_count=2,
    )
    db.add(album)
    db.flush()
    track1 = Track(album_id=album.id, path=str(first), ext="flac", format="FLAC", track_no=1)
    track2 = Track(album_id=album.id, path=str(second), ext="flac", format="FLAC", track_no=2)
    db.add_all([track1, track2])
    candidate = MatchCandidate(
        album_id=album.id,
        provider="musicbrainz",
        provider_id="mb-1",
        score=0.9,
        payload_json=_release().model_dump(mode="json"),
        raw_score_json={},
    )
    db.add(candidate)
    db.commit()
    return album, candidate, track1, track2


def test_fill_only_skips_non_empty(db, tmp_path):
    album, candidate, _, _ = _setup(db, tmp_path)
    plan = build_plan(db, album.id, candidate.id, "fill_only")
    fields = {(item.target_type, item.field) for item in plan.items}
    assert ("album", "ALBUM") not in fields
    assert ("album", "ALBUMARTIST") in fields
    assert ("track", "TITLE") in fields
    assert plan.status == "draft"


def test_overwrite_includes_existing(db, tmp_path):
    album, candidate, _, _ = _setup(db, tmp_path)
    plan = build_plan(db, album.id, candidate.id, "overwrite")
    fields = {(item.target_type, item.field) for item in plan.items}
    # unchanged values are not emitted as diffs
    assert ("album", "ALBUM") not in fields
    assert ("album", "ALBUMARTIST") in fields
    assert ("track", "TITLE") in fields


def test_whole_album_only_album_fields(db, tmp_path):
    album, candidate, _, _ = _setup(db, tmp_path, kind="whole")
    plan = build_plan(db, album.id, candidate.id, "fill_only")
    assert plan.items
    assert all(item.target_type == "album" for item in plan.items)
    assert all(item.target_id == album.id for item in plan.items)


def test_patch_items_toggles_selection(db, tmp_path):
    album, candidate, _, _ = _setup(db, tmp_path)
    plan = build_plan(db, album.id, candidate.id, "fill_only")
    item = plan.items[0]
    patch_items(db, plan.id, [{"id": item.id, "selected": False, "new_value": "手改值"}])
    db.refresh(item)
    assert item.selected is False
    assert item.new_value == "手改值"


def test_plan_cover_defaults_to_first_candidate(db, tmp_path):
    album, candidate, _, _ = _setup(db, tmp_path)
    plan = build_plan(db, album.id, candidate.id, "fill_only")
    assert plan.payload_json["cover_url"] == "https://example.com/cover.jpg"
    assert plan.payload_json["cover_provider"] == "musicbrainz"

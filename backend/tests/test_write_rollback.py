from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select

from app import tagio
from app.db.models import Album, Backup, ChangeItem, ChangePlan, LibraryRoot, Track
from app.services.backup import restore_batch
from app.services.cover import CoverError, process_cover, save_cover_jpg
from app.services.write import apply_plan

from .conftest import make_audio


def _setup_album(db, tmp_path: Path, *, readonly_second: bool = False):
    library = tmp_path / "library"
    directory = library / "A" / "Album"
    directory.mkdir(parents=True)
    first = make_audio(directory / "01.flac")
    second = make_audio(directory / "02.flac")
    tagio.write(first, {"TITLE": "旧标题", "ALBUM": "Album"})
    tagio.write(second, {"TITLE": "第二首", "ALBUM": "Album"})
    if readonly_second:
        os.chmod(second, 0o444)

    root = LibraryRoot(path=str(library))
    db.add(root)
    db.commit()
    album = Album(root_id=root.id, rel_path="A/Album", kind="split", status="pending")
    db.add(album)
    db.flush()
    track1 = Track(album_id=album.id, path=str(first), ext="flac", format="FLAC", track_no=1)
    track2 = Track(album_id=album.id, path=str(second), ext="flac", format="FLAC", track_no=2)
    db.add_all([track1, track2])
    db.flush()

    plan = ChangePlan(album_id=album.id, status="approved", policy="fill_only", payload_json={})
    db.add(plan)
    db.flush()
    db.add_all(
        [
            ChangeItem(
                plan_id=plan.id,
                target_type="album",
                target_id=album.id,
                field="ALBUMARTIST",
                old_value=None,
                new_value="甜梅号",
                selected=True,
            ),
            ChangeItem(
                plan_id=plan.id,
                target_type="track",
                target_id=track1.id,
                field="TITLE",
                old_value="旧标题",
                new_value="一个人的旅行",
                selected=True,
            ),
        ]
    )
    db.commit()
    return album, plan, first, second


@pytest.mark.asyncio
async def test_apply_writes_tags_and_backups(settings, db, tmp_path):
    album, plan, first, second = _setup_album(db, tmp_path)
    client = httpx.AsyncClient()
    result = await apply_plan(db, plan.id, client)
    await client.aclose()

    assert result["written"] == 2
    tags_first = tagio.read(first)
    assert tags_first["TITLE"] == ["一个人的旅行"]
    assert tags_first["ALBUMARTIST"] == ["甜梅号"]
    assert tagio.read(second)["ALBUMARTIST"] == ["甜梅号"]

    backups = db.scalar(select(func.count()).select_from(Backup))
    assert backups == 2
    db.refresh(plan)
    assert plan.status == "applied"


@pytest.mark.asyncio
async def test_apply_marks_album_matched(settings, db, tmp_path):
    album, plan, first, second = _setup_album(db, tmp_path)
    album.status = "unmatched"
    db.commit()

    client = httpx.AsyncClient()
    await apply_plan(db, plan.id, client)
    await client.aclose()

    db.refresh(album)
    assert album.status == "matched"


@pytest.mark.asyncio
async def test_rollback_restores_tags(settings, db, tmp_path):
    album, plan, first, second = _setup_album(db, tmp_path)
    client = httpx.AsyncClient()
    await apply_plan(db, plan.id, client)
    await client.aclose()

    result = restore_batch(db, f"plan-{plan.id}")
    assert result["restored"] == 2
    assert tagio.read(first)["TITLE"] == ["旧标题"]
    assert "ALBUMARTIST" not in tagio.read(first)
    db.refresh(plan)
    assert plan.status == "reverted"


@pytest.mark.asyncio
async def test_partial_failure_keeps_written_file(settings, db, tmp_path):
    album, plan, first, second = _setup_album(db, tmp_path, readonly_second=True)
    client = httpx.AsyncClient()
    result = await apply_plan(db, plan.id, client)
    await client.aclose()

    assert result["written"] == 1
    assert result["errors"]
    db.refresh(plan)
    assert plan.status == "failed"
    assert tagio.read(first)["TITLE"] == ["一个人的旅行"]

    os.chmod(second, 0o644)
    restore_batch(db, f"plan-{plan.id}")
    assert tagio.read(first)["TITLE"] == ["旧标题"]


def test_cover_policy_if_missing(tmp_path):
    target = tmp_path / "cover.jpg"
    target.write_bytes(b"old")
    assert save_cover_jpg(tmp_path, b"new", "if_missing") is None
    assert target.read_bytes() == b"old"
    assert save_cover_jpg(tmp_path, b"new", "always") == target
    assert target.read_bytes() == b"new"


@pytest.mark.asyncio
async def test_apply_with_cover_embeds_and_writes_jpg(settings, db, tmp_path):
    from io import BytesIO

    from PIL import Image

    album, plan, first, second = _setup_album(db, tmp_path)
    image = Image.new("RGB", (800, 800), (184, 98, 45))
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    cover = buffer.getvalue()

    # serve the cover without hitting the network
    async def fake_download(client, url, **kwargs):
        return cover

    import app.services.write as write_module

    original = write_module.download_cover
    write_module.download_cover = fake_download
    plan.payload_json = {"cover_url": "https://example.com/cover.jpg"}
    db.commit()
    try:
        client = httpx.AsyncClient()
        await apply_plan(db, plan.id, client)
        await client.aclose()
    finally:
        write_module.download_cover = original

    assert len(tagio.snapshot(first).images) == 1
    assert (Path(first).parent / "cover.jpg").exists()


def _jpeg(width: int, height: int) -> bytes:
    from io import BytesIO

    from PIL import Image

    image = Image.new("RGB", (width, height), (184, 98, 45))
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def test_process_cover_accepts_tall_cover_with_short_side_under_500():
    processed = process_cover(_jpeg(451, 600))
    assert processed


def test_process_cover_rejects_low_resolution_cover():
    with pytest.raises(CoverError):
        process_cover(_jpeg(300, 300))


@pytest.mark.asyncio
async def test_apply_falls_back_to_larger_cover(settings, db, tmp_path):
    album, plan, first, second = _setup_album(db, tmp_path)
    small = _jpeg(300, 300)
    large = _jpeg(640, 640)
    requested: list[str] = []

    async def fake_download(client, url, **kwargs):
        requested.append(url)
        return small if "small" in url else large

    import app.services.write as write_module

    original = write_module.download_cover
    write_module.download_cover = fake_download
    plan.payload_json = {
        "cover_url": "https://example.com/small.jpg",
        "release": {
            "covers": [
                {"provider": "spotify", "url": "https://example.com/small.jpg", "width": 300, "height": 300},
                {"provider": "spotify", "url": "https://example.com/large.jpg", "width": 640, "height": 640},
            ]
        },
    }
    db.commit()
    try:
        client = httpx.AsyncClient()
        result = await apply_plan(db, plan.id, client)
        await client.aclose()
    finally:
        write_module.download_cover = original

    assert result["cover_error"] is None
    assert "https://example.com/large.jpg" in requested
    assert len(tagio.snapshot(first).images) == 1
    assert (Path(first).parent / "cover.jpg").exists()

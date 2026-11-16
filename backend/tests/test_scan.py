from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from app import tagio
from app.api.deps import serialize_album
from app.db.models import Album, LibraryRoot
from app.services.scan import scan_root

from .conftest import make_audio, make_silence


def _add_root(db, path: Path) -> LibraryRoot:
    root = LibraryRoot(path=str(path))
    db.add(root)
    db.commit()
    db.refresh(root)
    return root


def _write_track(path: Path, *, album: str, artist: str, title: str, number: str) -> None:
    make_audio(path)
    tagio.write(
        path,
        {
            "ALBUM": album,
            "ALBUMARTIST": artist,
            "ARTIST": artist,
            "TITLE": title,
            "TRACKNUMBER": number,
            "TRACKTOTAL": "2",
            "DATE": "2010",
        },
    )


def test_scan_split_album(db, tmp_path):
    library = tmp_path / "library"
    directory = library / "甜梅号" / "城市天气 (2010)"
    _write_track(directory / "01 - 一个人的旅行.flac", album="城市天气", artist="甜梅号", title="一个人的旅行", number="1")
    _write_track(directory / "02 - 城市天气.flac", album="城市天气", artist="甜梅号", title="城市天气", number="2")
    (directory / "cover.jpg").write_bytes(b"x")
    (directory / "notes.nfo").write_text("nfo")

    root = _add_root(db, library)
    result = scan_root(db, root)
    album = db.scalar(select(Album))

    assert result.albums == 1
    assert result.files == 2
    assert album is not None
    assert album.kind == "split"
    assert album.track_count == 2
    assert album.artist == "甜梅号"
    assert album.album == "城市天气"
    assert album.year == 2010
    assert [track.title for track in album.tracks] == ["一个人的旅行", "城市天气"]


def test_whole_when_cue_present(db, tmp_path):
    library = tmp_path / "library"
    directory = library / "Keith Jarrett" / "The Köln Concert (1975)"
    make_audio(directory / "Köln.flac", seconds=3)
    (directory / "Köln.cue").write_text(
        'PERFORMER "Keith Jarrett"\nTITLE "The Köln Concert"\nFILE "Köln.flac" WAVE\n'
        "  TRACK 01 AUDIO\n    TITLE \"Part I\"\n    PERFORMER \"Keith Jarrett\"\n    INDEX 01 00:00:00\n",
        encoding="utf-8",
    )

    root = _add_root(db, library)
    scan_root(db, root)
    album = db.scalar(select(Album))
    assert album is not None
    assert album.kind == "whole"


def test_whole_cue_parsed_into_track_list(db, tmp_path):
    library = tmp_path / "library"
    directory = library / "Keith Jarrett" / "The Köln Concert (1975)"
    make_audio(directory / "Köln.flac", seconds=3)
    (directory / "Köln.cue").write_text(
        'PERFORMER "Keith Jarrett"\nTITLE "The Köln Concert"\nFILE "Köln.flac" WAVE\n'
        "  TRACK 01 AUDIO\n    TITLE \"Part I\"\n    PERFORMER \"Keith Jarrett\"\n    INDEX 01 00:00:00\n"
        "  TRACK 02 AUDIO\n    TITLE \"Part II\"\n    INDEX 01 00:01:00\n",
        encoding="utf-8",
    )

    root = _add_root(db, library)
    scan_root(db, root)
    album = db.scalar(select(Album))

    assert album is not None
    assert album.kind == "whole"
    assert album.track_count == 2
    assert len(album.tracks) == 1
    cue_tracks = album.cue_tracks_json
    assert [track["track_no"] for track in cue_tracks] == [1, 2]
    assert [track["title"] for track in cue_tracks] == ["Part I", "Part II"]
    assert cue_tracks[0]["duration_ms"] == 1000
    assert cue_tracks[1]["duration_ms"] == 2000
    assert cue_tracks[1]["artist"] == "Keith Jarrett"


def test_cue_change_triggers_rescan(db, tmp_path):
    library = tmp_path / "library"
    directory = library / "Keith Jarrett" / "The Köln Concert (1975)"
    make_audio(directory / "Köln.flac", seconds=3)
    cue = directory / "Köln.cue"
    cue.write_text(
        'FILE "Köln.flac" WAVE\n'
        "  TRACK 01 AUDIO\n    TITLE \"Part I\"\n    INDEX 01 00:00:00\n",
        encoding="utf-8",
    )

    root = _add_root(db, library)
    first = scan_root(db, root)
    second = scan_root(db, root)
    assert first.parsed_files == 1
    assert second.parsed_files == 0

    cue.write_text(
        'FILE "Köln.flac" WAVE\n'
        "  TRACK 01 AUDIO\n    TITLE \"Part I\"\n    INDEX 01 00:00:00\n"
        "  TRACK 02 AUDIO\n    TITLE \"Part II\"\n    INDEX 01 00:01:00\n",
        encoding="utf-8",
    )
    third = scan_root(db, root)
    assert third.parsed_files == 1
    album = db.scalar(select(Album))
    assert album is not None
    assert album.track_count == 2


def test_single_file_over_15min_is_whole(db, tmp_path):
    library = tmp_path / "library"
    directory = library / "Ambient" / "Long Player"
    make_silence(directory / "album.flac", seconds=901)

    root = _add_root(db, library)
    scan_root(db, root)
    album = db.scalar(select(Album))
    assert album is not None
    assert album.kind == "whole"
    assert album.track_count == 1
    assert album.cue_tracks_json == []


def test_incremental_scan_skips_unchanged(db, tmp_path):
    library = tmp_path / "library"
    directory = library / "A" / "B"
    _write_track(directory / "01 - one.flac", album="B", artist="A", title="one", number="1")

    root = _add_root(db, library)
    first = scan_root(db, root)
    second = scan_root(db, root)
    assert first.parsed_files == 1
    assert second.parsed_files == 0


def test_scan_removes_deleted_album(db, tmp_path):
    library = tmp_path / "library"
    directory = library / "A" / "B"
    _write_track(directory / "01 - one.flac", album="B", artist="A", title="one", number="1")

    root = _add_root(db, library)
    scan_root(db, root)
    assert db.scalar(select(Album)) is not None

    for path in directory.iterdir():
        path.unlink()
    directory.rmdir()
    scan_root(db, root)
    assert db.scalar(select(Album)) is None


def test_serialize_album_detail_includes_cue_tracks(db, tmp_path):
    library = tmp_path / "library"
    directory = library / "Keith Jarrett" / "The Köln Concert (1975)"
    make_audio(directory / "Köln.flac", seconds=3)
    (directory / "Köln.cue").write_text(
        'PERFORMER "Keith Jarrett"\nTITLE "The Köln Concert"\nFILE "Köln.flac" WAVE\n'
        "  TRACK 01 AUDIO\n    TITLE \"Part I\"\n    INDEX 01 00:00:00\n",
        encoding="utf-8",
    )

    root = _add_root(db, library)
    scan_root(db, root)
    album = db.scalar(select(Album))
    assert album is not None

    payload = serialize_album(album, detail=True)
    assert payload["track_count"] == 1
    assert payload["cue_tracks"] == [
        {"track_no": 1, "title": "Part I", "artist": "Keith Jarrett", "duration_ms": 3000}
    ]
    assert len(payload["tracks"]) == 1


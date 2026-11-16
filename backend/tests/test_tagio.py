from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from app import tagio
from app.tagio.service import UnsupportedFormat

from .conftest import make_audio


def jpeg(size: int = 600) -> bytes:
    image = Image.new("RGB", (size, size), (184, 98, 45))
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def test_flac_roundtrip_chinese(tmp_path):
    path = make_audio(tmp_path / "a.flac")
    tagio.write(
        path,
        {
            "ALBUMARTIST": "甜梅号",
            "ALBUM": "城市天气",
            "TITLE": "一个人的旅行",
            "DATE": "2010",
            "TRACKNUMBER": "1",
            "TRACKTOTAL": "9",
        },
    )
    tags = tagio.read(path)
    assert tags["ALBUMARTIST"] == ["甜梅号"]
    assert tags["ALBUM"] == ["城市天气"]
    assert tags["TITLE"] == ["一个人的旅行"]
    assert tags["TRACKNUMBER"] == ["1"]
    assert tags["TRACKTOTAL"] == ["9"]


def test_mp3_roundtrip_and_special_chars(tmp_path):
    path = make_audio(tmp_path / "b.mp3")
    tagio.write(
        path,
        {
            "TITLE": "Café / 東京 — ✨",
            "ARTIST": "A & B",
            "ALBUM": "Mixes",
            "TRACKNUMBER": "3",
            "TRACKTOTAL": "12",
            "ISRC": "TWAE31000101",
        },
    )
    tags = tagio.read(path)
    assert tags["TITLE"] == ["Café / 東京 — ✨"]
    assert tags["ARTIST"] == ["A & B"]
    assert tags["TRACKNUMBER"] == ["3"]
    assert tags["TRACKTOTAL"] == ["12"]
    assert tags["ISRC"] == ["TWAE31000101"]


def test_m4a_roundtrip(tmp_path):
    path = make_audio(tmp_path / "c.m4a")
    tagio.write(
        path,
        {
            "TITLE": "城市天气",
            "ARTIST": "甜梅号",
            "ALBUM": "城市天气",
            "TRACKNUMBER": "2",
            "TRACKTOTAL": "9",
            "CATALOGNUMBER": "RB-045",
        },
    )
    tags = tagio.read(path)
    assert tags["TITLE"] == ["城市天气"]
    assert tags["TRACKNUMBER"] == ["2"]
    assert tags["TRACKTOTAL"] == ["9"]
    assert tags["CATALOGNUMBER"] == ["RB-045"]


def test_wav_id3_roundtrip(tmp_path):
    path = make_audio(tmp_path / "d.wav")
    tagio.write(path, {"TITLE": "月光", "ARTIST": "李泉"})
    tags = tagio.read(path)
    assert tags["TITLE"] == ["月光"]
    assert tags["ARTIST"] == ["李泉"]


def test_cover_embed_flac(tmp_path):
    path = make_audio(tmp_path / "e.flac")
    tagio.write(path, {"TITLE": "cover"}, jpeg())
    snapshot = tagio.snapshot(path)
    assert len(snapshot.images) == 1
    assert snapshot.images[0]["mime"] == "image/jpeg"


def test_snapshot_restore(tmp_path):
    path = make_audio(tmp_path / "f.flac")
    tagio.write(path, {"TITLE": "original", "ARTIST": "someone"}, jpeg())
    snapshot = tagio.snapshot(path)
    tagio.write(path, {"TITLE": "changed", "ALBUM": "new"})
    tagio.restore(path, snapshot)
    tags = tagio.read(path)
    assert tags["TITLE"] == ["original"]
    assert "ALBUM" not in tags
    assert len(tagio.snapshot(path).images) == 1


def test_unsupported_format(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("hello")
    with pytest.raises(UnsupportedFormat):
        tagio.read(path)

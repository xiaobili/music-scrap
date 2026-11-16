from __future__ import annotations

import base64
import mimetypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import mutagen
from mutagen.apev2 import APEv2
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, TXXX, Frames, ID3
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover, MP4FreeForm
from mutagen.oggvorbis import OggVorbis
from mutagen.wave import WAVE

from .mapping import (
    APE_KEYS,
    ID3_TEXT,
    ID3_TXXX,
    MP4_ATOMS,
    MP4_FREEFORM,
    UNIFIED_FIELDS,
)


class UnsupportedFormat(Exception):
    pass


@dataclass
class Snapshot:
    format: str
    tags: dict[str, Any]
    images: list[dict[str, Any]] = field(default_factory=list)


_FRAME_BY_ID = {frame_id: cls for frame_id, cls in Frames.items()}


def _values(value: str | list[str] | tuple[str, ...] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item) != ""]
    return [str(value)] if str(value) != "" else []


def _split_pair(out: dict[str, list[str]], number_key: str, total_key: str) -> None:
    values = out.get(number_key)
    if not values:
        return
    raw = values[0]
    if "/" in raw:
        number, total = raw.split("/", 1)
        out[number_key] = [number]
        out[total_key] = [total]


def _normalize_read(out: dict[str, list[str]]) -> dict[str, list[str]]:
    _split_pair(out, "TRACKNUMBER", "TRACKTOTAL")
    _split_pair(out, "DISCNUMBER", "DISCTOTAL")
    return {key: values for key, values in out.items() if values}


def _read_vorbis(audio: FLAC | OggVorbis) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for key in UNIFIED_FIELDS:
        values = audio.get(key)
        if values:
            out[key] = [str(item) for item in values]
    return _normalize_read(out)


def _write_vorbis(audio: FLAC | OggVorbis, fields: dict[str, str]) -> None:
    for key, value in fields.items():
        if key not in UNIFIED_FIELDS:
            continue
        values = _values(value)
        if values:
            audio[key] = values
        elif key in audio:
            del audio[key]


def _read_id3(tags: ID3) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for key, frame_id in ID3_TEXT.items():
        frame = tags.get(frame_id)
        text = getattr(frame, "text", None) if frame is not None else None
        if text:
            out[key] = [str(item) for item in text]

    for key, desc in ID3_TXXX.items():
        for frame in tags.getall("TXXX"):
            if str(frame.desc).upper() == desc.upper() and frame.text:
                out[key] = [str(item) for item in frame.text]

    track = tags.get("TRCK")
    if track and getattr(track, "text", None):
        out["TRACKNUMBER"] = [str(track.text[0])]
    disc = tags.get("TPOS")
    if disc and getattr(disc, "text", None):
        out["DISCNUMBER"] = [str(disc.text[0])]
    return _normalize_read(out)


def _set_track_pair(tags: ID3, fields: dict[str, str]) -> None:
    if "TRACKNUMBER" not in fields and "TRACKTOTAL" not in fields:
        return
    current = tags.get("TRCK")
    number = fields.get("TRACKNUMBER")
    total = fields.get("TRACKTOTAL")
    if current and getattr(current, "text", None):
        existing = str(current.text[0])
        if "/" in existing:
            old_number, old_total = existing.split("/", 1)
            number = number if number is not None else old_number
            total = total if total is not None else old_total
        elif number is None:
            number = existing
    if not number and not total:
        tags.delall("TRCK")
        return
    value = f"{number or ''}/{total}" if total else (number or "")
    tags.delall("TRCK")
    tags.add(Frames["TRCK"](encoding=3, text=[value]))


def _set_disc_pair(tags: ID3, fields: dict[str, str]) -> None:
    if "DISCNUMBER" not in fields and "DISCTOTAL" not in fields:
        return
    current = tags.get("TPOS")
    number = fields.get("DISCNUMBER")
    total = fields.get("DISCTOTAL")
    if current and getattr(current, "text", None):
        existing = str(current.text[0])
        if "/" in existing:
            old_number, old_total = existing.split("/", 1)
            number = number if number is not None else old_number
            total = total if total is not None else old_total
        elif number is None:
            number = existing
    if not number and not total:
        tags.delall("TPOS")
        return
    value = f"{number or ''}/{total}" if total else (number or "")
    tags.delall("TPOS")
    tags.add(Frames["TPOS"](encoding=3, text=[value]))


def _apply_id3(tags: ID3, fields: dict[str, str]) -> None:
    for key, frame_id in ID3_TEXT.items():
        if key not in fields:
            continue
        tags.delall(frame_id)
        value = fields.get(key)
        if value:
            tags.add(Frames[frame_id](encoding=3, text=[value]))

    for key, desc in ID3_TXXX.items():
        if key not in fields:
            continue
        tags.delall(f"TXXX:{desc}")
        value = fields.get(key)
        if value:
            tags.add(TXXX(encoding=3, desc=desc, text=[value]))

    _set_track_pair(tags, fields)
    _set_disc_pair(tags, fields)


def _read_mp4(audio: MP4) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    if not audio.tags:
        return out
    for key, atom in MP4_ATOMS.items():
        values = audio.tags.get(atom)
        if values:
            out[key] = [str(item) for item in values]
    for key, name in MP4_FREEFORM.items():
        atom = f"----:com.apple.iTunes:{name}"
        values = audio.tags.get(atom)
        if values:
            out[key] = [
                item.decode("utf-8", "replace") if isinstance(item, bytes) else str(item)
                for item in values
            ]
    track = audio.tags.get("trkn")
    if track:
        number, total = track[0]
        if number:
            out["TRACKNUMBER"] = [str(number)]
        if total:
            out["TRACKTOTAL"] = [str(total)]
    disc = audio.tags.get("disk")
    if disc:
        number, total = disc[0]
        if number:
            out["DISCNUMBER"] = [str(number)]
        if total:
            out["DISCTOTAL"] = [str(total)]
    return _normalize_read(out)


def _apply_mp4(audio: MP4, fields: dict[str, str]) -> None:
    if audio.tags is None:
        audio.add_tags()
    assert audio.tags is not None

    for key, atom in MP4_ATOMS.items():
        if key not in fields:
            continue
        value = fields.get(key)
        if value:
            audio.tags[atom] = [value]
        elif atom in audio.tags:
            del audio.tags[atom]

    for key, name in MP4_FREEFORM.items():
        if key not in fields:
            continue
        atom = f"----:com.apple.iTunes:{name}"
        value = fields.get(key)
        if value:
            audio.tags[atom] = [MP4FreeForm(value.encode("utf-8"))]
        elif atom in audio.tags:
            del audio.tags[atom]

    if "TRACKNUMBER" in fields or "TRACKTOTAL" in fields:
        existing = audio.tags.get("trkn", [(0, 0)])[0]
        number = fields.get("TRACKNUMBER")
        total = fields.get("TRACKTOTAL")
        audio.tags["trkn"] = [
            (
                int(number) if number else int(existing[0]),
                int(total) if total else int(existing[1]),
            )
        ]
    if "DISCNUMBER" in fields or "DISCTOTAL" in fields:
        existing = audio.tags.get("disk", [(0, 0)])[0]
        number = fields.get("DISCNUMBER")
        total = fields.get("DISCTOTAL")
        audio.tags["disk"] = [
            (
                int(number) if number else int(existing[0]),
                int(total) if total else int(existing[1]),
            )
        ]


def _read_ape(path: Path) -> dict[str, list[str]]:
    try:
        tags = APEv2(path)
    except Exception:
        return {}
    out: dict[str, list[str]] = {}
    reverse = {ape_key.lower(): key for key, ape_key in APE_KEYS.items()}
    for ape_key in tags.keys():
        key = reverse.get(ape_key.lower())
        if not key:
            continue
        out[key] = [str(tags[ape_key])]
    return _normalize_read(out)


def _apply_ape(path: Path, fields: dict[str, str]) -> None:
    try:
        tags = APEv2(path)
    except Exception:
        tags = APEv2()
    for key, ape_key in APE_KEYS.items():
        if key not in fields:
            continue
        value = fields.get(key)
        if value:
            tags[ape_key] = [value]
        elif ape_key in tags:
            del tags[ape_key]
    tags.save(path)


def _open_id3(path: Path) -> ID3:
    suffix = path.suffix.lower()
    if suffix == ".mp3":
        audio = MP3(path, ID3=ID3)
        if audio.tags is None:
            audio.add_tags()
        return audio.tags
    audio = WAVE(path)
    if audio.tags is None:
        audio.add_tags()
    return audio.tags


def _save_id3(path: Path, tags: ID3) -> None:
    if path.suffix.lower() == ".mp3":
        tags.save(path)
    else:
        audio = WAVE(path)
        audio.tags = tags
        audio.save()


def read(path: Path | str) -> dict[str, list[str]]:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".flac":
        return _read_vorbis(FLAC(path))
    if suffix == ".ogg":
        return _read_vorbis(OggVorbis(path))
    if suffix in {".mp3", ".wav"}:
        return _read_id3(_open_id3(path))
    if suffix in {".m4a", ".mp4"}:
        return _read_mp4(MP4(path))
    if suffix == ".ape":
        return _read_ape(path)
    raise UnsupportedFormat(suffix)


def write(
    path: Path | str,
    fields: dict[str, str],
    cover_jpeg: bytes | None = None,
) -> None:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".flac":
        audio = FLAC(path)
        _write_vorbis(audio, fields)
        if cover_jpeg is not None:
            audio.clear_pictures()
            picture = Picture()
            picture.type = 3
            picture.mime = "image/jpeg"
            picture.desc = "Cover"
            picture.data = cover_jpeg
            audio.add_picture(picture)
        audio.save()
        return
    if suffix == ".ogg":
        audio = OggVorbis(path)
        _write_vorbis(audio, fields)
        if cover_jpeg is not None:
            picture = Picture()
            picture.type = 3
            picture.mime = "image/jpeg"
            picture.desc = "Cover"
            picture.data = cover_jpeg
            audio["metadata_block_picture"] = [
                base64.b64encode(picture.write()).decode("ascii")
            ]
        audio.save()
        return
    if suffix in {".mp3", ".wav"}:
        tags = _open_id3(path)
        _apply_id3(tags, fields)
        if cover_jpeg is not None:
            tags.delall("APIC")
            tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover_jpeg))
        _save_id3(path, tags)
        return
    if suffix in {".m4a", ".mp4"}:
        audio = MP4(path)
        _apply_mp4(audio, fields)
        if cover_jpeg is not None:
            audio.tags["covr"] = [MP4Cover(cover_jpeg, imageformat=MP4Cover.FORMAT_JPEG)]
        audio.save()
        return
    if suffix == ".ape":
        _apply_ape(path, fields)
        return
    raise UnsupportedFormat(suffix)


def probe(path: Path | str) -> dict[str, Any]:
    audio = mutagen.File(path)
    if audio is None:
        raise UnsupportedFormat(Path(path).suffix.lower())
    info = audio.info
    return {
        "duration_ms": int(getattr(info, "length", 0) * 1000),
        "bitrate": int(getattr(info, "bitrate", 0) or 0),
        "sample_rate": int(getattr(info, "sample_rate", 0) or 0),
        "format": type(audio).__name__,
    }


def snapshot(path: Path | str) -> Snapshot:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".flac":
        audio = FLAC(path)
        images = [
            {"mime": pic.mime, "type": pic.type, "desc": pic.desc, "data": pic.data}
            for pic in audio.pictures
        ]
        return Snapshot("flac", {key: list(values) for key, values in audio.items()}, images)
    if suffix == ".ogg":
        audio = OggVorbis(path)
        images = []
        for item in audio.get("metadata_block_picture", []) or []:
            try:
                picture = Picture(base64.b64decode(item))
            except Exception:
                continue
            images.append(
                {"mime": picture.mime, "type": picture.type, "desc": picture.desc, "data": picture.data}
            )
        tags = {key: list(values) for key, values in audio.items() if key != "metadata_block_picture"}
        return Snapshot("ogg", tags, images)
    if suffix in {".mp3", ".wav"}:
        tags = _open_id3(path)
        frames: list[dict[str, Any]] = []
        images: list[dict[str, Any]] = []
        for frame in tags.values():
            if frame.FrameID == "APIC":
                images.append(
                    {
                        "mime": frame.mime,
                        "type": frame.type,
                        "desc": frame.desc,
                        "data": frame.data,
                    }
                )
                continue
            if frame.FrameID == "TXXX":
                frames.append(
                    {"id": "TXXX", "desc": frame.desc, "text": [str(x) for x in frame.text]}
                )
            elif getattr(frame, "text", None) is not None:
                frames.append({"id": frame.FrameID, "text": [str(x) for x in frame.text]})
        return Snapshot("id3", {"frames": frames}, images)
    if suffix in {".m4a", ".mp4"}:
        audio = MP4(path)
        tags: dict[str, Any] = {}
        images: list[dict[str, Any]] = []
        for key, value in (audio.tags or {}).items():
            if key == "covr":
                for cover in value:
                    images.append(
                        {
                            "mime": "image/jpeg"
                            if cover.imageformat == MP4Cover.FORMAT_JPEG
                            else "image/png",
                            "type": 3,
                            "desc": "Cover",
                            "data": bytes(cover),
                        }
                    )
                continue
            if isinstance(value, list):
                tags[key] = [
                    item.decode("utf-8", "replace") if isinstance(item, bytes) else item
                    for item in value
                ]
            else:
                tags[key] = value
        return Snapshot("mp4", tags, images)
    if suffix == ".ape":
        try:
            ape = APEv2(path)
        except Exception:
            return Snapshot("ape", {}, [])
        return Snapshot("ape", {key: str(ape[key]) for key in ape.keys()}, [])
    raise UnsupportedFormat(suffix)


def restore(path: Path | str, snap: Snapshot) -> None:
    path = Path(path)
    if snap.format in {"flac", "ogg"}:
        audio = FLAC(path) if snap.format == "flac" else OggVorbis(path)
        for key in list(audio.keys()):
            if key == "metadata_block_picture":
                continue
            del audio[key]
        for key, values in snap.tags.items():
            audio[key] = list(values)
        if snap.format == "flac":
            audio.clear_pictures()
            for image in snap.images:
                picture = Picture()
                picture.type = int(image.get("type") or 3)
                picture.mime = image.get("mime") or "image/jpeg"
                picture.desc = image.get("desc") or ""
                picture.data = image["data"]
                audio.add_picture(picture)
        else:
            encoded = []
            for image in snap.images:
                picture = Picture()
                picture.type = int(image.get("type") or 3)
                picture.mime = image.get("mime") or "image/jpeg"
                picture.desc = image.get("desc") or ""
                picture.data = image["data"]
                encoded.append(base64.b64encode(picture.write()).decode("ascii"))
            if encoded:
                audio["metadata_block_picture"] = encoded
        audio.save()
        return
    if snap.format == "id3":
        tags = _open_id3(path)
        for key in list(tags.keys()):
            del tags[key]
        for frame_data in snap.tags.get("frames", []):
            frame_id = frame_data["id"]
            if frame_id == "TXXX":
                tags.add(
                    TXXX(
                        encoding=3,
                        desc=frame_data.get("desc", ""),
                        text=list(frame_data.get("text", [])),
                    )
                )
            elif frame_id in _FRAME_BY_ID:
                tags.add(
                    _FRAME_BY_ID[frame_id](
                        encoding=3, text=list(frame_data.get("text", []))
                    )
                )
        for image in snap.images:
            tags.add(
                APIC(
                    encoding=3,
                    mime=image.get("mime") or "image/jpeg",
                    type=int(image.get("type") or 3),
                    desc=image.get("desc") or "",
                    data=image["data"],
                )
            )
        _save_id3(path, tags)
        return
    if snap.format == "mp4":
        audio = MP4(path)
        if audio.tags is None:
            audio.add_tags()
        assert audio.tags is not None
        for key in list(audio.tags.keys()):
            del audio.tags[key]
        for key, values in snap.tags.items():
            if key == "covr":
                continue
            if key in {"trkn", "disk"} and isinstance(values, list) and len(values) == 2:
                audio.tags[key] = [(int(values[0]), int(values[1]))]
            elif isinstance(values, list) and values and isinstance(values[0], str):
                if key.startswith("----:"):
                    audio.tags[key] = [MP4FreeForm(item.encode("utf-8")) for item in values]
                else:
                    audio.tags[key] = values
            else:
                audio.tags[key] = values
        if snap.images:
            covers = []
            for image in snap.images:
                fmt = (
                    MP4Cover.FORMAT_PNG
                    if (image.get("mime") or "").endswith("png")
                    else MP4Cover.FORMAT_JPEG
                )
                covers.append(MP4Cover(image["data"], imageformat=fmt))
            audio.tags["covr"] = covers
        audio.save()
        return
    if snap.format == "ape":
        try:
            tags = APEv2(path)
        except Exception:
            tags = APEv2()
        for key in list(tags.keys()):
            del tags[key]
        for key, value in snap.tags.items():
            tags[key] = [value]
        tags.save(path)
        return
    raise UnsupportedFormat(snap.format)


def image_extension(mime: str) -> str:
    return mimetypes.guess_extension(mime) or ".bin"

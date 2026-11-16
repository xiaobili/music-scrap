from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import tagio
from ..core.paths import PathViolation, resolve_inside_roots
from ..db.models import Album, LibraryRoot, Track
from ..tagio.mapping import AUDIO_EXTENSIONS

CUE_TRACK_RE = re.compile(r"^\s*TRACK\s+(\d+)\s+AUDIO", re.IGNORECASE)
CUE_TITLE_RE = re.compile(r'^\s*TITLE\s+"?([^"]+)"?', re.IGNORECASE)
CUE_PERFORMER_RE = re.compile(r'^\s*PERFORMER\s+"?([^"]+)"?', re.IGNORECASE)
CUE_INDEX_RE = re.compile(r"^\s*INDEX\s+01\s+(\d+):(\d+):(\d+)", re.IGNORECASE)
YEAR_RE = re.compile(r"(19|20)\d{2}")
TRACK_FILE_RE = re.compile(r"^\s*(\d{1,3})\s*[-._\s]+(.+)$")

ProgressCallback = Callable[[int, int, str], None]


@dataclass
class DirHints:
    artist: str | None = None
    album: str | None = None
    year: int | None = None


@dataclass
class ScannedFile:
    path: Path
    rel_path: str
    size: int
    mtime_ns: int
    duration_ms: int = 0
    tags: dict[str, list[str]] = field(default_factory=dict)
    title: str | None = None
    track_no: int | None = None
    disc_no: int | None = None
    bitrate: int = 0
    sample_rate: int = 0


@dataclass
class ScanResult:
    albums: int = 0
    files: int = 0
    parsed_files: int = 0


def parse_dir_hints(rel_dir: Path) -> DirHints:
    parts = [part for part in rel_dir.parts if part not in (".", "")]
    if not parts:
        return DirHints()
    album_raw = parts[-1]
    artist = parts[-2] if len(parts) >= 2 else None
    year_match = YEAR_RE.search(album_raw)
    year = int(year_match.group(0)) if year_match else None
    album = album_raw
    if year:
        album = re.sub(r"[\(\[]?\b" + str(year) + r"\b[\)\]]?", "", album)
    album = re.sub(r"^\s*\d{4}\s*[-._]\s*", "", album)
    album = album.strip(" -._")
    return DirHints(artist=artist, album=album or album_raw, year=year)


def parse_track_filename(stem: str) -> tuple[int | None, str]:
    match = TRACK_FILE_RE.match(stem)
    if match:
        return int(match.group(1)), match.group(2).strip()
    return None, stem.strip()


def parse_cue(path: Path, total_ms: int = 0) -> dict[str, object]:
    tracks: list[dict[str, object]] = []
    album_title: str | None = None
    album_artist: str | None = None
    current: dict[str, object] | None = None
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {"title": None, "artist": None, "tracks": []}
    for line in lines:
        track_match = CUE_TRACK_RE.match(line)
        if track_match:
            current = {
                "track_no": int(track_match.group(1)),
                "title": None,
                "artist": None,
                "start_ms": None,
            }
            tracks.append(current)
            continue
        title_match = CUE_TITLE_RE.match(line)
        if title_match:
            if current is None:
                album_title = title_match.group(1).strip()
            else:
                current["title"] = title_match.group(1).strip()
            continue
        performer_match = CUE_PERFORMER_RE.match(line)
        if performer_match:
            if current is None:
                album_artist = performer_match.group(1).strip()
            else:
                current["artist"] = performer_match.group(1).strip()
            continue
        index_match = CUE_INDEX_RE.match(line)
        if index_match and current is not None:
            minutes, seconds, frames = (int(group) for group in index_match.groups())
            current["start_ms"] = minutes * 60_000 + seconds * 1000 + round(frames * 1000 / 75)

    for index, track in enumerate(tracks):
        if track["artist"] is None:
            track["artist"] = album_artist
        start = track.pop("start_ms")
        if start is None:
            track["duration_ms"] = 0
            continue
        next_start = tracks[index + 1]["start_ms"] if index + 1 < len(tracks) else None
        end = next_start if next_start is not None else (total_ms or start)
        track["duration_ms"] = max(int(end) - int(start), 0)
    return {"title": album_title, "artist": album_artist, "tracks": tracks}


def find_cue_files(directory: Path) -> list[Path]:
    try:
        return sorted(
            (
                path
                for path in directory.iterdir()
                if path.suffix.lower() == ".cue" and path.is_file()
            ),
            key=lambda path: path.name.lower(),
        )
    except OSError:
        return []


def _iter_audio_files(root: Path) -> list[tuple[Path, Path]]:
    found: list[tuple[Path, Path]] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [name for name in dirnames if not name.startswith(".")]
        directory = Path(dirpath)
        for filename in filenames:
            if filename.startswith("."):
                continue
            path = directory / filename
            if path.suffix.lower() not in AUDIO_EXTENSIONS:
                continue
            if path.is_symlink():
                continue
            try:
                resolve_inside_roots(path, [root], must_exist=True)
            except PathViolation:
                continue
            found.append((path, path.parent))
    return found


def compute_file_sig(files: list[ScannedFile], cue_files: list[Path] | None = None) -> str:
    parts = [f"{item.rel_path}|{item.size}|{item.mtime_ns}" for item in files]
    for cue in cue_files or []:
        try:
            stat = cue.stat()
        except OSError:
            continue
        parts.append(f"cue:{cue.name}|{stat.st_size}|{stat.st_mtime_ns}")
    return hashlib.sha256("\n".join(sorted(parts)).encode("utf-8")).hexdigest()


def _first(tags: dict[str, list[str]], key: str) -> str | None:
    values = tags.get(key)
    return values[0] if values else None


def _detect_kind(directory_files: list[ScannedFile], cue_present: bool) -> str:
    if cue_present:
        return "whole"
    if len(directory_files) == 1 and directory_files[0].duration_ms > 15 * 60 * 1000:
        return "whole"
    return "split"


def scan_root(
    session: Session,
    root: LibraryRoot,
    progress: ProgressCallback | None = None,
    *,
    force: bool = False,
) -> ScanResult:
    root_path = Path(root.path)
    result = ScanResult()
    audio_files = _iter_audio_files(root_path)
    result.files = len(audio_files)

    grouped: dict[Path, list[tuple[Path, Path]]] = {}
    for path, directory in audio_files:
        grouped.setdefault(directory, []).append((path, directory))

    seen_rel: set[str] = set()
    total = len(grouped)
    for index, (directory, entries) in enumerate(sorted(grouped.items(), key=lambda item: str(item[0])), start=1):
        rel_dir = directory.relative_to(root_path)
        rel_key = rel_dir.as_posix() or "."
        seen_rel.add(rel_key)

        scanned: list[ScannedFile] = []
        for path, _ in sorted(entries, key=lambda item: item[0].name.lower()):
            stat = path.stat()
            item = ScannedFile(
                path=path,
                rel_path=path.relative_to(root_path).as_posix(),
                size=stat.st_size,
                mtime_ns=stat.st_mtime_ns,
            )
            try:
                item.tags = tagio.read(path)
                info = tagio.probe(path)
                item.duration_ms = int(info["duration_ms"])
                item.bitrate = int(info["bitrate"])
                item.sample_rate = int(info["sample_rate"])
            except Exception:
                item.tags = {}
            item.track_no, item.title = parse_track_filename(path.stem)
            if item.tags.get("TRACKNUMBER"):
                try:
                    item.track_no = int(item.tags["TRACKNUMBER"][0])
                except ValueError:
                    pass
            if item.tags.get("TITLE"):
                item.title = item.tags["TITLE"][0]
            if item.tags.get("DISCNUMBER"):
                try:
                    item.disc_no = int(item.tags["DISCNUMBER"][0])
                except ValueError:
                    pass
            scanned.append(item)

        cue_files = find_cue_files(directory)
        total_duration_ms = sum(item.duration_ms for item in scanned)
        cue = (
            parse_cue(cue_files[0], total_duration_ms)
            if cue_files
            else {"title": None, "artist": None, "tracks": []}
        )
        cue_tracks = cue["tracks"]
        signature = compute_file_sig(scanned, cue_files)
        album = session.scalar(
            select(Album).where(Album.root_id == root.id, Album.rel_path == rel_key)
        )
        if album and album.file_sig == signature and not force:
            result.albums += 1
            if progress:
                progress(index, total, f"跳过未变目录 {rel_key}")
            continue

        kind = _detect_kind(scanned, bool(cue_files))
        hints = parse_dir_hints(rel_dir)

        first_tags = scanned[0].tags if scanned else {}
        album_artist = (
            _first(first_tags, "ALBUMARTIST")
            or _first(first_tags, "ARTIST")
            or cue["artist"]
            or hints.artist
        )
        album_title = _first(first_tags, "ALBUM") or cue["title"] or hints.album
        date_value = _first(first_tags, "DATE") or ""
        year = int(date_value[:4]) if date_value[:4].isdigit() else hints.year

        if album is None:
            album = Album(root_id=root.id, rel_path=rel_key)
            session.add(album)
            session.flush()

        album.kind = kind
        album.artist = album_artist
        album.album = album_title
        album.year = year
        album.file_sig = signature
        album.cue_tracks_json = cue_tracks if kind == "whole" else []
        album.track_count = len(cue_tracks) if album.cue_tracks_json else len(scanned)
        album.duration_ms = total_duration_ms

        existing_tracks = {track.path: track for track in album.tracks}
        keep_paths: set[str] = set()
        for item in scanned:
            keep_paths.add(str(item.path))
            track = existing_tracks.get(str(item.path))
            if track is None:
                track = Track(album_id=album.id, path=str(item.path), ext=item.path.suffix.lower().lstrip("."))
                session.add(track)
            track.format = item.path.suffix.lower().lstrip(".").upper()
            track.track_no = item.track_no
            track.disc_no = item.disc_no
            track.title = item.title
            track.artist = _first(item.tags, "ARTIST") or album_artist
            track.duration_ms = item.duration_ms
            track.bitrate = item.bitrate
            track.sample_rate = item.sample_rate
            track.isrc = _first(item.tags, "ISRC")
            track.mbid = _first(item.tags, "MUSICBRAINZ_TRACKID")
        for path, track in existing_tracks.items():
            if path not in keep_paths:
                session.delete(track)

        result.albums += 1
        result.parsed_files += len(scanned)
        if progress:
            progress(index, total, f"解析 {rel_key}")

    for album in list(session.scalars(select(Album).where(Album.root_id == root.id)).all()):
        if album.rel_path not in seen_rel:
            session.delete(album)

    root.last_scan_at = datetime.now(timezone.utc)
    session.commit()
    return result

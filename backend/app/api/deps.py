from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
from fastapi import Request
from sqlalchemy.orm import Session

from ..db.models import Album, AuditLog, Backup, Job, LibraryRoot, MatchCandidate, Track
from ..db.session import get_session as _get_session


def get_db() -> Iterator[Session]:
    yield from _get_session()


def get_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.client


def serialize_job(job: Job) -> dict[str, Any]:
    return {
        "id": job.id,
        "type": job.type,
        "status": job.status,
        "progress": job.progress,
        "total": job.total,
        "done": job.done,
        "payload": job.payload_json,
        "result": job.result_json,
        "error": job.error,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }


def album_directory(album: Album) -> Path | None:
    for track in album.tracks:
        return Path(track.path).parent
    return None


def album_cover_path(album: Album) -> Path | None:
    directory = album_directory(album)
    if directory is None:
        return None
    cover = directory / "cover.jpg"
    return cover if cover.exists() else None


def serialize_album(album: Album, *, detail: bool = False) -> dict[str, Any]:
    cover = album_cover_path(album)
    payload: dict[str, Any] = {
        "id": album.id,
        "root_id": album.root_id,
        "rel_path": album.rel_path,
        "kind": album.kind,
        "status": album.status,
        "artist": album.artist,
        "title": album.album,
        "year": album.year,
        "track_count": album.track_count,
        "duration_ms": album.duration_ms,
        "confidence": round(album.confidence or 0.0, 4),
        "mbid": album.mbid,
        "has_cover": cover is not None,
        "cover_url": f"/api/albums/{album.id}/cover" if cover else None,
        "selected_cover_url": album.cover_url,
    }
    if detail:
        payload["tracks"] = [
            {
                "id": track.id,
                "path": track.path,
                "ext": track.ext,
                "format": track.format,
                "track_no": track.track_no,
                "disc_no": track.disc_no,
                "title": track.title,
                "artist": track.artist,
                "duration_ms": track.duration_ms,
                "bitrate": track.bitrate,
                "sample_rate": track.sample_rate,
            }
            for track in album.tracks
        ]
        payload["cue_tracks"] = album.cue_tracks_json or []
        payload["directory"] = str(album_directory(album) or "") or None
    return payload


def serialize_root(root: LibraryRoot) -> dict[str, Any]:
    return {
        "id": root.id,
        "path": root.path,
        "enabled": root.enabled,
        "last_scan_at": root.last_scan_at.isoformat() if root.last_scan_at else None,
        "album_count": len(root.albums),
    }


def serialize_candidate(candidate: MatchCandidate) -> dict[str, Any]:
    payload = candidate.payload_json or {}
    return {
        "id": candidate.id,
        "provider": candidate.provider,
        "provider_id": candidate.provider_id,
        "score": round(candidate.score, 4),
        "parts": candidate.raw_score_json,
        "title": payload.get("title"),
        "artist": payload.get("artist"),
        "year": payload.get("year"),
        "label": payload.get("label"),
        "catalog_number": payload.get("catalog_number"),
        "track_count": len(payload.get("tracks") or []),
        "duration_ms": sum(
            int(track.get("duration_ms") or 0) for track in payload.get("tracks") or []
        ),
        "release_mbid": payload.get("release_mbid"),
        "covers": payload.get("covers") or [],
        "fetched_at": candidate.fetched_at.isoformat() if candidate.fetched_at else None,
    }


def serialize_backup_row(row: Backup) -> dict[str, Any]:
    return {
        "id": row.id,
        "album_id": row.album_id,
        "batch_id": row.batch_id,
        "target_path": row.target_path,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def serialize_audit(row: AuditLog) -> dict[str, Any]:
    return {
        "id": row.id,
        "action": row.action,
        "entity": row.entity,
        "entity_id": row.entity_id,
        "detail": row.detail_json,
        "trace_id": row.trace_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def track_tags(track: Track) -> dict[str, list[str]]:
    from .. import tagio

    try:
        return tagio.read(track.path)
    except Exception:
        return {}

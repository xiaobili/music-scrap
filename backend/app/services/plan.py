from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import tagio
from ..db.models import Album, ChangeItem, ChangePlan, MatchCandidate, Track
from ..providers.base import CanonicalRelease, CoverCandidate
from .settings import SettingsStore

ALBUM_TARGET = "album"
TRACK_TARGET = "track"


def _release_values(release: CanonicalRelease) -> dict[str, str | None]:
    return {
        "ALBUM": release.title,
        "ALBUMARTIST": release.artist,
        "DATE": str(release.year) if release.year else None,
        "GENRE": "; ".join(release.genres) if release.genres else None,
        "LABEL": release.label,
        "CATALOGNUMBER": release.catalog_number,
        "BARCODE": release.barcode,
        "MUSICBRAINZ_ALBUMID": release.release_mbid
        or (release.provider_id if release.provider == "musicbrainz" else None),
    }


def _track_values(
    release: CanonicalRelease, remote_index: int, track_total: int, disc_total: int
) -> dict[str, str | None]:
    remote = release.tracks[remote_index]
    return {
        "TITLE": remote.title,
        "ARTIST": remote.artist or release.artist,
        "TRACKNUMBER": str(remote.position),
        "TRACKTOTAL": str(track_total),
        "DISCNUMBER": str(remote.disc),
        "DISCTOTAL": str(disc_total),
        "ISRC": remote.isrc,
        "MUSICBRAINZ_TRACKID": remote.mbid,
    }


def _make_item(
    plan_id: int,
    target_type: str,
    target_id: int | None,
    field: str,
    old: str | None,
    new: str | None,
    policy: str,
) -> ChangeItem | None:
    if new is None or str(new).strip() == "":
        return None
    old_value = old or None
    if policy == "fill_only":
        if old_value:
            return None
    elif policy == "overwrite":
        if old_value == new:
            return None
    action = "add" if not old_value else ("same" if old_value == str(new) else "update")
    return ChangeItem(
        plan_id=plan_id,
        target_type=target_type,
        target_id=target_id,
        field=field,
        old_value=old_value,
        new_value=str(new),
        action=action,
        selected=True,
    )


def _cover_area(cover: CoverCandidate) -> int:
    return int(cover.width or 0) * int(cover.height or 0)


def _default_cover(release: CanonicalRelease) -> CoverCandidate | None:
    if not release.covers:
        return None
    return max(release.covers, key=_cover_area)


def _resolve_cover(
    album: Album, release: CanonicalRelease
) -> tuple[str | None, str | None]:
    """优先保留用户选中的封面，但它已不属于当前候选时改用当前候选的最大封面。"""
    default_cover = _default_cover(release)
    if not album.cover_url:
        return (default_cover.url, default_cover.provider) if default_cover else (None, None)
    for cover in release.covers:
        if cover.url == album.cover_url:
            return cover.url, cover.provider
    if default_cover is not None:
        return default_cover.url, default_cover.provider
    return album.cover_url, None


def _match_remote_index(track: Track, index: int, remote_count: int) -> int:
    if remote_count == 0:
        return -1
    if track.track_no:
        return min(max(track.track_no - 1, 0), remote_count - 1)
    return min(index, remote_count - 1)


def build_plan(
    session: Session,
    album_id: int,
    candidate_id: int,
    policy: str | None = None,
) -> ChangePlan:
    album = session.get(Album, album_id)
    candidate = session.get(MatchCandidate, candidate_id)
    if album is None or candidate is None:
        raise ValueError("album or candidate not found")
    if candidate.album_id != album.id:
        raise ValueError("candidate does not belong to album")

    # 人工选定候选即视为匹配完成，避免低置信度专辑写入后仍停留在 unmatched
    album.status = "matched"

    if policy is None:
        policy = str(SettingsStore(session).get("field_policy") or "fill_only")

    release = CanonicalRelease.model_validate(candidate.payload_json)
    tracks = list(
        session.scalars(
            select(Track).where(Track.album_id == album.id).order_by(Track.disc_no, Track.track_no)
        ).all()
    )

    session.execute(
        delete(ChangePlan).where(
            ChangePlan.album_id == album.id, ChangePlan.status == "draft"
        )
    )
    cover_url, cover_provider = _resolve_cover(album, release)
    plan = ChangePlan(
        album_id=album.id,
        status="draft",
        policy=policy,
        payload_json={
            "candidate_id": candidate.id,
            "provider": release.provider,
            "provider_id": release.provider_id,
            "release": release.model_dump(mode="json"),
            "cover_url": cover_url,
            "cover_provider": cover_provider,
        },
    )
    session.add(plan)
    session.flush()

    album_values = _release_values(release)
    remote_tracks = release.tracks
    disc_total = max((track.disc for track in remote_tracks), default=1)

    tag_cache: dict[str, dict[str, list[str]]] = {}
    for index, track in enumerate(tracks):
        try:
            current = tagio.read(track.path)
        except Exception:
            current = {}
        tag_cache[track.path] = current

        for field, value in album_values.items():
            old = (current.get(field) or [None])[0]
            item = _make_item(plan.id, ALBUM_TARGET, album.id, field, old, value, policy)
            if item:
                session.add(item)
                current.setdefault(field, []).append(str(value))

        if album.kind == "whole":
            continue

        remote_index = _match_remote_index(track, index, len(remote_tracks))
        if remote_index < 0:
            continue
        track_values = _track_values(release, remote_index, len(remote_tracks), disc_total)
        for field, value in track_values.items():
            old = (current.get(field) or [None])[0]
            item = _make_item(plan.id, TRACK_TARGET, track.id, field, old, value, policy)
            if item:
                session.add(item)
                current.setdefault(field, []).append(str(value))

    session.commit()
    session.refresh(plan)
    return plan


def patch_items(session: Session, plan_id: int, updates: list[dict[str, Any]]) -> ChangePlan:
    plan = session.get(ChangePlan, plan_id)
    if plan is None:
        raise ValueError("plan not found")
    if plan.status in {"applied", "reverted"}:
        raise ValueError("plan is already finalized")
    for update in updates:
        item = session.get(ChangeItem, int(update.get("id", 0)))
        if item is None or item.plan_id != plan.id:
            continue
        if "selected" in update:
            item.selected = bool(update["selected"])
        if "new_value" in update:
            item.new_value = update["new_value"]
    session.commit()
    session.refresh(plan)
    return plan


def approve_plan(session: Session, plan_id: int) -> ChangePlan:
    plan = session.get(ChangePlan, plan_id)
    if plan is None:
        raise ValueError("plan not found")
    if plan.status == "draft":
        plan.status = "approved"
        session.commit()
    return plan


def plan_payload(plan: ChangePlan) -> dict[str, Any]:
    album = plan.album
    items = []
    for item in plan.items:
        items.append(
            {
                "id": item.id,
                "target_type": item.target_type,
                "target_id": item.target_id,
                "field": item.field,
                "old_value": item.old_value,
                "new_value": item.new_value,
                "action": item.action,
                "selected": item.selected,
            }
        )
    return {
        "id": plan.id,
        "album_id": plan.album_id,
        "status": plan.status,
        "policy": plan.policy,
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
        "candidate_id": (plan.payload_json or {}).get("candidate_id"),
        "cover_url": (plan.payload_json or {}).get("cover_url"),
        "cover_provider": (plan.payload_json or {}).get("cover_provider"),
        "release": (plan.payload_json or {}).get("release"),
        "album": {
            "id": album.id,
            "artist": album.artist,
            "title": album.album,
            "year": album.year,
            "kind": album.kind,
        },
        "items": items,
        "file_count": len(album.tracks),
        "selected_count": sum(1 for item in plan.items if item.selected),
        "total_count": len(plan.items),
    }

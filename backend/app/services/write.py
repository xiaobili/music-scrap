from __future__ import annotations

import os
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Callable

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import tagio
from ..core.logging import trace_id_var
from ..db.models import Album, AuditLog, ChangeItem, ChangePlan, Track
from ..providers.base import CanonicalRelease
from .backup import create_backup
from .cover import CoverError, download_cover, process_cover, save_cover_jpg
from .settings import SettingsStore

ProgressCallback = Callable[[int, int, str], None]
CancelCheck = Callable[[], bool]


class VerificationError(Exception):
    pass


def _safe_write(
    path: Path, fields: dict[str, str], cover: bytes | None, safe_mode: bool
) -> None:
    if not safe_mode:
        tagio.write(path, fields, cover)
        return
    temp = path.with_name(f".{path.stem}.music-scrap{path.suffix}")
    shutil.copy2(path, temp)
    try:
        tagio.write(temp, fields, cover)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _verify(path: Path, fields: dict[str, str], cover: bytes | None) -> None:
    current = tagio.read(path)
    for field, expected in fields.items():
        actual = (current.get(field) or [""])[0]
        if actual != expected:
            raise VerificationError(f"{field}: expected {expected!r}, got {actual!r}")
    if cover is not None and path.suffix.lower() != ".ape":
        snapshot = tagio.snapshot(path)
        if not snapshot.images:
            raise VerificationError("embedded cover missing after write")


async def apply_plan(
    session: Session,
    plan_id: int,
    client: httpx.AsyncClient,
    progress: ProgressCallback | None = None,
    is_cancelled: CancelCheck | None = None,
) -> dict[str, object]:
    plan = session.get(ChangePlan, plan_id)
    if plan is None:
        raise ValueError("plan not found")
    if plan.status == "applied":
        return {"written": 0, "errors": [], "skipped": True}

    album = session.get(Album, plan.album_id)
    if album is None:
        raise ValueError("album not found")

    # 有可执行的变更计划说明已完成人工匹配，写入时兜底修正历史遗留状态
    album.status = "matched"

    tracks = list(
        session.scalars(
            select(Track).where(Track.album_id == album.id).order_by(Track.disc_no, Track.track_no)
        ).all()
    )
    items = list(
        session.scalars(select(ChangeItem).where(ChangeItem.plan_id == plan.id)).all()
    )

    album_fields: dict[str, str] = {}
    track_fields: dict[int, dict[str, str]] = defaultdict(dict)
    for item in items:
        if not item.selected or item.new_value is None:
            continue
        if item.target_type == "album":
            album_fields[item.field] = item.new_value
        elif item.target_type == "track" and item.target_id is not None:
            track_fields[item.target_id][item.field] = item.new_value

    store = SettingsStore(session)
    cover_policy = str(store.get("cover_policy") or "if_missing")
    safe_mode = bool(store.get("safe_mode"))

    cover_bytes = None
    cover_error = None
    payload = plan.payload_json or {}
    release_covers = (payload.get("release") or {}).get("covers") or []
    selected_cover = payload.get("cover_url")
    provider_urls = {cover.get("url") for cover in release_covers if cover.get("url")}
    cover_urls = [selected_cover] if selected_cover else []
    if selected_cover in provider_urls:
        for cover in sorted(
            release_covers,
            key=lambda item: int(item.get("width") or 0) * int(item.get("height") or 0),
            reverse=True,
        ):
            url = cover.get("url")
            if url and url not in cover_urls:
                cover_urls.append(url)
    for url in cover_urls:
        try:
            raw = await download_cover(client, url)
            cover_bytes = process_cover(raw)
            cover_error = None
            break
        except (CoverError, httpx.HTTPError) as exc:
            cover_error = str(exc)

    batch_id = f"plan-{plan.id}"
    errors: list[dict[str, str]] = []
    written = 0
    prepared_dirs: set[Path] = set()

    for index, track in enumerate(tracks, start=1):
        if is_cancelled and is_cancelled():
            errors.append({"path": str(track.path), "error": "cancelled"})
            break

        fields = dict(album_fields)
        fields.update(track_fields.get(track.id, {}))
        caretaker_cover = cover_bytes is not None and downward_cover_enabled(
            cover_policy, Path(track.path).parent / "cover.jpg"
        )
        if not fields and not caretaker_cover:
            if progress:
                progress(index, len(tracks), f"跳过 {Path(track.path).name}")
            continue

        path = Path(track.path)
        cover_path = path.parent / "cover.jpg"
        first_in_dir = path.parent not in prepared_dirs

        try:
            create_backup(
                session,
                album_id=album.id,
                plan_id=plan.id,
                batch_id=batch_id,
                path=path,
                cover_path=cover_path if (caretaker_cover and first_in_dir) else None,
            )
            session.commit()
            _safe_write(path, fields, cover_bytes, safe_mode)
            _verify(path, fields, cover_bytes)
            if caretaker_cover and first_in_dir and cover_bytes is not None:
                save_cover_jpg(path.parent, cover_bytes, cover_policy)
                prepared_dirs.add(path.parent)
            written += 1
        except Exception as exc:
            errors.append({"path": str(path), "error": str(exc)})
            session.rollback()
            # re-fetch plan because rollback expires objects
            plan = session.get(ChangePlan, plan_id)
            if plan is None:
                break

        if progress:
            progress(index, len(tracks), f"写入 {path.name}")

    plan = session.get(ChangePlan, plan_id)
    if plan is not None:
        plan.status = "applied" if not errors else "failed"
    release_payload = (plan.payload_json or {}).get("release") if plan else None
    if release_payload and album.mbid is None:
        album.mbid = release_payload.get("release_mbid")
    session.add(
        AuditLog(
            action="apply_plan",
            entity="change_plan",
            entity_id=plan_id,
            detail_json={
                "written": written,
                "errors": errors,
                "cover_error": cover_error,
                "batch_id": batch_id,
            },
            trace_id=trace_id_var.get(),
        )
    )
    session.commit()

    return {
        "written": written,
        "total": len(tracks),
        "errors": errors,
        "cover_error": cover_error,
        "batch_id": batch_id,
    }


def downward_cover_enabled(policy: str, cover_path: Path) -> bool:
    if policy == "never":
        return False
    if policy == "if_missing":
        return not cover_path.exists()
    return True

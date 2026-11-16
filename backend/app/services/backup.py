from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import tagio
from ..core.config import get_settings
from ..db.models import Backup, ChangePlan
from ..tagio.service import Snapshot

ProgressCallback = Callable[[int, int, str], None]


def backup_root() -> Path:
    root = get_settings().backup_dir
    root.mkdir(parents=True, exist_ok=True)
    return root


def create_backup(
    session: Session,
    *,
    album_id: int,
    plan_id: int | None,
    batch_id: str,
    path: Path,
    cover_path: Path | None = None,
) -> Backup:
    snapshot = tagio.snapshot(path)
    directory = backup_root() / str(album_id) / batch_id
    images_dir = directory / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    images_meta: list[dict[str, str]] = []
    for index, image in enumerate(snapshot.images):
        extension = tagio.service.image_extension(image.get("mime") or "image/jpeg")
        filename = f"{path.stem}-{index}{extension}"
        (images_dir / filename).write_bytes(image["data"])
        images_meta.append(
            {
                "mime": image.get("mime") or "image/jpeg",
                "type": str(image.get("type") or 3),
                "desc": image.get("desc") or "",
                "file": filename,
            }
        )

    cover_before = None
    created_cover = False
    if cover_path is not None:
        if cover_path.exists():
            cover_before = "cover-before.jpg"
            (directory / cover_before).write_bytes(cover_path.read_bytes())
        else:
            created_cover = True

    snapshot_json = {
        "format": snapshot.format,
        "tags": snapshot.tags,
        "images": images_meta,
        "created_cover": created_cover,
        "cover_before": cover_before,
    }
    serialized = json.dumps(snapshot_json, ensure_ascii=False, sort_keys=True)
    file_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    row = Backup(
        album_id=album_id,
        plan_id=plan_id,
        batch_id=batch_id,
        target_path=str(path),
        snapshot_json=snapshot_json,
        image_files_json=images_meta,
        file_hash=file_hash,
    )
    session.add(row)
    session.flush()
    return row


def load_snapshot(row: Backup) -> Snapshot:
    payload = row.snapshot_json or {}
    directory = backup_root() / str(row.album_id) / row.batch_id / "images"
    images = []
    for meta in payload.get("images", []) or []:
        file_path = directory / meta.get("file", "")
        if not file_path.exists():
            continue
        images.append(
            {
                "mime": meta.get("mime") or "image/jpeg",
                "type": int(meta.get("type") or 3),
                "desc": meta.get("desc") or "",
                "data": file_path.read_bytes(),
            }
        )
    return Snapshot(
        format=payload.get("format", "flac"),
        tags=payload.get("tags") or {},
        images=images,
    )


def restore_batch(
    session: Session,
    batch_id: str,
    progress: ProgressCallback | None = None,
) -> dict[str, object]:
    rows = list(
        session.scalars(select(Backup).where(Backup.batch_id == batch_id).order_by(Backup.id)).all()
    )
    restored = 0
    errors: list[dict[str, str]] = []
    plan_id: int | None = None

    for index, row in enumerate(rows, start=1):
        plan_id = row.plan_id
        path = Path(row.target_path)
        try:
            if not path.exists():
                raise FileNotFoundError(str(path))
            snapshot = load_snapshot(row)
            tagio.restore(path, snapshot)
            cover = path.parent / "cover.jpg"
            payload = row.snapshot_json or {}
            cover_before = payload.get("cover_before")
            if cover_before:
                backup_cover = backup_root() / str(row.album_id) / row.batch_id / cover_before
                if backup_cover.exists():
                    cover.write_bytes(backup_cover.read_bytes())
            elif payload.get("created_cover") and cover.exists():
                cover.unlink()
            restored += 1
        except Exception as exc:
            errors.append({"path": str(path), "error": str(exc)})
        if progress:
            progress(index, len(rows), f"还原 {path.name}")

    if plan_id:
        plan = session.get(ChangePlan, plan_id)
        if plan is not None:
            plan.status = "reverted"
    session.commit()
    return {"restored": restored, "errors": errors, "total": len(rows)}

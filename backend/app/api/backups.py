from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Album, Backup, ChangePlan
from ..jobs.runner import get_runner
from .deps import album_cover_path, get_db

router = APIRouter()


@router.get("/backups")
def list_backups(
    album_id: int | None = None, session: Session = Depends(get_db)
) -> list[dict[str, object]]:
    stmt = select(Backup).order_by(Backup.id.desc())
    if album_id:
        stmt = stmt.where(Backup.album_id == album_id)
    rows = session.scalars(stmt).all()

    groups: dict[str, dict[str, object]] = {}
    for row in rows:
        group = groups.get(row.batch_id)
        album = session.get(Album, row.album_id)
        plan = session.get(ChangePlan, row.plan_id) if row.plan_id else None
        cover = album_cover_path(album) if album is not None else None
        if group is None:
            group = {
                "batch_id": row.batch_id,
                "backup_id": row.id,
                "album_id": row.album_id,
                "album_title": album.album if album else None,
                "artist": album.artist if album else None,
                "cover_url": f"/api/albums/{row.album_id}/cover" if cover else None,
                "plan_id": row.plan_id,
                "status": plan.status if plan else "unknown",
                "files": 0,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            groups[row.batch_id] = group
        group["files"] = int(group["files"]) + 1
    return list(groups.values())


@router.post("/backups/{batch}/restore")
def restore_backup(batch: str, session: Session = Depends(get_db)) -> dict[str, object]:
    batch_id = batch
    if batch.isdigit():
        row = session.get(Backup, int(batch))
        if row is not None:
            batch_id = row.batch_id
    exists = session.scalar(select(Backup.id).where(Backup.batch_id == batch_id))
    if exists is None:
        raise HTTPException(status_code=404, detail="backup batch not found")
    job = get_runner().enqueue("rollback", {"batch_id": batch_id})
    return {"job_id": job.id, "status": job.status, "batch_id": batch_id}

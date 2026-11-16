from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import Album, Job, LibraryRoot, Track
from .deps import get_db, serialize_album

router = APIRouter()


@router.get("/stats")
def stats(session: Session = Depends(get_db)) -> dict[str, object]:
    albums = session.scalar(select(func.count()).select_from(Album)) or 0
    files = session.scalar(select(func.count()).select_from(Track)) or 0
    pending = (
        session.scalar(
            select(func.count())
            .select_from(Album)
            .where(Album.status.in_(["pending", "unmatched"]))
        )
        or 0
    )
    roots = session.scalar(select(func.count()).select_from(LibraryRoot)) or 0
    running = (
        session.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.status.in_(["queued", "running"]))
        )
        or 0
    )
    recent = session.scalars(
        select(Album).order_by(Album.updated_at.desc(), Album.id.desc()).limit(5)
    ).all()
    return {
        "albums": albums,
        "files": files,
        "pending": pending,
        "roots": roots,
        "running_jobs": running,
        "recent_albums": [serialize_album(album) for album in recent],
    }

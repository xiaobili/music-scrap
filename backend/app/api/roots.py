from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.paths import PathViolation
from ..db.models import LibraryRoot
from ..jobs.runner import get_runner
from ..schemas import JobCreated, RootCreate, RootPatch
from .deps import get_db, serialize_root

router = APIRouter()


@router.get("/roots")
def list_roots(session: Session = Depends(get_db)) -> list[dict[str, object]]:
    roots = session.scalars(select(LibraryRoot).order_by(LibraryRoot.id)).all()
    return [serialize_root(root) for root in roots]


@router.post("/roots", status_code=201)
def create_root(payload: RootCreate, session: Session = Depends(get_db)) -> dict[str, object]:
    try:
        path = Path(payload.path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=f"invalid path: {exc}") from exc
    if not path.is_dir():
        raise HTTPException(status_code=400, detail="path must be a directory")
    if session.scalar(select(LibraryRoot).where(LibraryRoot.path == str(path))):
        raise HTTPException(status_code=409, detail="root already exists")
    root = LibraryRoot(path=str(path))
    session.add(root)
    session.commit()
    session.refresh(root)
    return serialize_root(root)


@router.patch("/roots/{root_id}")
def patch_root(
    root_id: int, payload: RootPatch, session: Session = Depends(get_db)
) -> dict[str, object]:
    root = session.get(LibraryRoot, root_id)
    if root is None:
        raise HTTPException(status_code=404, detail="root not found")
    root.enabled = payload.enabled
    session.commit()
    return serialize_root(root)


@router.delete("/roots/{root_id}", status_code=204)
def delete_root(root_id: int, session: Session = Depends(get_db)) -> None:
    root = session.get(LibraryRoot, root_id)
    if root is None:
        raise HTTPException(status_code=404, detail="root not found")
    session.delete(root)
    session.commit()


@router.post("/roots/{root_id}/scan", response_model=JobCreated)
def scan_root(root_id: int, session: Session = Depends(get_db)) -> JobCreated:
    root = session.get(LibraryRoot, root_id)
    if root is None:
        raise HTTPException(status_code=404, detail="root not found")
    if not root.enabled:
        raise HTTPException(status_code=400, detail="root is disabled")
    try:
        Path(root.path).resolve(strict=True)
    except (OSError, RuntimeError, PathViolation) as exc:
        raise HTTPException(status_code=400, detail=f"root is not accessible: {exc}") from exc
    job = get_runner().enqueue("scan", {"root_id": root.id})
    return JobCreated(job_id=job.id, status=job.status)

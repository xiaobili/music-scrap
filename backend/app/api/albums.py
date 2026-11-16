from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import Album, ChangePlan, MatchCandidate
from ..jobs.runner import get_runner
from ..schemas import AlbumSearchRequest, CoverSelectRequest, SelectCandidateRequest
from ..services.cover import CoverError, process_cover
from ..services.match import get_cover_candidates, match_album
from ..services.plan import build_plan, plan_payload
from .deps import (
    album_cover_path,
    album_directory,
    get_client,
    get_db,
    serialize_album,
    serialize_candidate,
    track_tags,
)

router = APIRouter()


@router.get("/albums")
def list_albums(
    status: str | None = None,
    kind: str | None = None,
    root_id: int | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 24,
    session: Session = Depends(get_db),
) -> dict[str, object]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    stmt = select(Album)
    if status:
        stmt = stmt.where(Album.status == status)
    if kind:
        stmt = stmt.where(Album.kind == kind)
    if root_id:
        stmt = stmt.where(Album.root_id == root_id)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            (Album.album.ilike(pattern))
            | (Album.artist.ilike(pattern))
            | (Album.rel_path.ilike(pattern))
        )
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    albums = session.scalars(
        stmt.order_by(Album.updated_at.desc(), Album.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "items": [serialize_album(album) for album in albums],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/albums/batch/match")
def batch_match(
    payload: dict, session: Session = Depends(get_db)
) -> dict[str, object]:
    album_ids = payload.get("album_ids") or []
    jobs: list[int] = []
    for raw_id in album_ids[:50]:
        album = session.get(Album, int(raw_id))
        if album is None:
            continue
        jobs.append(get_runner().enqueue("match", {"album_id": album.id}).id)
    return {"job_ids": jobs}


@router.get("/albums/{album_id}")
def album_detail(album_id: int, session: Session = Depends(get_db)) -> dict[str, object]:
    album = session.get(Album, album_id)
    if album is None:
        raise HTTPException(status_code=404, detail="album not found")
    payload = serialize_album(album, detail=True)
    tags = {str(track.id): track_tags(track) for track in album.tracks}
    album_tags = next(iter(tags.values()), {})
    payload["tags"] = album_tags
    payload["track_tags"] = tags
    payload["candidates_count"] = len(album.candidates)
    payload["has_cover"] = album_cover_path(album) is not None
    return payload


@router.get("/albums/{album_id}/candidates")
def album_candidates(
    album_id: int, session: Session = Depends(get_db)
) -> list[dict[str, object]]:
    album = session.get(Album, album_id)
    if album is None:
        raise HTTPException(status_code=404, detail="album not found")
    candidates = session.scalars(
        select(MatchCandidate)
        .where(MatchCandidate.album_id == album.id)
        .order_by(MatchCandidate.score.desc())
    ).all()
    return [serialize_candidate(candidate) for candidate in candidates]


@router.post("/albums/{album_id}/search")
async def search_album(
    album_id: int,
    payload: AlbumSearchRequest,
    session: Session = Depends(get_db),
    client=Depends(get_client),
) -> list[dict[str, object]]:
    album = session.get(Album, album_id)
    if album is None:
        raise HTTPException(status_code=404, detail="album not found")
    rows = await match_album(session, album.id, client, manual_query=payload.query)
    return [serialize_candidate(row) for row in rows]


@router.post("/albums/{album_id}/select")
def select_candidate(
    album_id: int,
    payload: SelectCandidateRequest,
    session: Session = Depends(get_db),
) -> dict[str, object]:
    try:
        plan = build_plan(session, album_id, payload.candidate_id, payload.policy)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.refresh(plan)
    return plan_payload(plan)


@router.get("/albums/{album_id}/covers")
async def album_covers(
    album_id: int,
    candidate_id: int = Query(...),
    session: Session = Depends(get_db),
    client=Depends(get_client),
) -> list[dict[str, object]]:
    try:
        return await get_cover_candidates(session, album_id, candidate_id, client)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/albums/{album_id}/cover")
def select_cover(
    album_id: int,
    payload: CoverSelectRequest,
    session: Session = Depends(get_db),
) -> dict[str, object]:
    album = session.get(Album, album_id)
    if album is None:
        raise HTTPException(status_code=404, detail="album not found")
    plan = None
    if payload.plan_id:
        plan = session.get(ChangePlan, payload.plan_id)
    else:
        plan = session.scalar(
            select(ChangePlan)
            .where(
                ChangePlan.album_id == album.id,
                ChangePlan.status.in_(["draft", "approved"]),
            )
            .order_by(ChangePlan.id.desc())
        )
    if plan is None or plan.album_id != album.id:
        plan = None
    album.cover_url = payload.url
    if plan is not None:
        plan.payload_json = {**(plan.payload_json or {}), "cover_url": payload.url}
    session.commit()
    return {
        "plan_id": plan.id if plan is not None else None,
        "cover_url": payload.url,
    }


@router.post("/albums/{album_id}/cover/upload")
def upload_cover(
    album_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    album = session.get(Album, album_id)
    if album is None:
        raise HTTPException(status_code=404, detail="album not found")
    directory = album_directory(album)
    if directory is None:
        raise HTTPException(status_code=400, detail="album has no files")
    data = file.file.read()
    try:
        jpeg = process_cover(data)
    except CoverError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    target = Path(directory) / "cover.jpg"
    target.write_bytes(jpeg)
    return {"cover_url": f"/api/albums/{album.id}/cover"}


@router.get("/albums/{album_id}/cover")
def get_cover(album_id: int, session: Session = Depends(get_db)) -> FileResponse:
    album = session.get(Album, album_id)
    if album is None:
        raise HTTPException(status_code=404, detail="album not found")
    cover = album_cover_path(album)
    if cover is None:
        raise HTTPException(status_code=404, detail="cover not found")
    return FileResponse(cover, media_type="image/jpeg")

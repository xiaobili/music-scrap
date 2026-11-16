from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Job
from ..db.session import get_session_factory
from ..jobs.runner import get_runner
from .deps import get_db, serialize_job

router = APIRouter()

TERMINAL = {"succeeded", "failed", "cancelled"}


@router.get("/jobs")
def list_jobs(
    limit: int = 50, session: Session = Depends(get_db)
) -> list[dict[str, object]]:
    jobs = session.scalars(select(Job).order_by(Job.id.desc()).limit(min(limit, 200))).all()
    return [serialize_job(job) for job in jobs]


@router.get("/jobs/{job_id}")
def get_job(job_id: int, session: Session = Depends(get_db)) -> dict[str, object]:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return serialize_job(job)


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: int, session: Session = Depends(get_db)) -> dict[str, object]:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    get_runner().cancel(job_id)
    session.refresh(job)
    return serialize_job(job)


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: int, request: Request) -> StreamingResponse:
    async def generator():
        last_payload: str | None = None
        while True:
            if await request.is_disconnected():
                break
            with get_session_factory()() as session:
                job = session.get(Job, job_id)
                if job is None:
                    yield 'event: error\ndata: {"message":"job not found"}\n\n'
                    break
                payload = serialize_job(job)
                status = job.status
            serialized = json.dumps(payload, ensure_ascii=False)
            if serialized != last_payload:
                event = "done" if status in TERMINAL else "progress"
                yield f"event: {event}\ndata: {serialized}\n\n"
                last_payload = serialized
                if status in TERMINAL:
                    break
            await asyncio.sleep(0.5)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

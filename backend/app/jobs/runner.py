from __future__ import annotations

import asyncio
import traceback
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ..db.models import Job, LibraryRoot
from ..services.backup import restore_batch
from ..services.match import match_album
from ..services.scan import scan_root
from ..services.write import apply_plan


class JobRunner:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        client: httpx.AsyncClient,
        workers: int = 3,
    ):
        self.session_factory = session_factory
        self.client = client
        self.workers = workers
        self._queue: asyncio.Queue[int] = asyncio.Queue()
        self._tasks: list[asyncio.Task[None]] = []
        self._cancelled: set[int] = set()
        self._semaphores = {
            "scan": asyncio.Semaphore(1),
            "match": asyncio.Semaphore(3),
            "apply": asyncio.Semaphore(1),
            "rollback": asyncio.Semaphore(1),
        }

    async def start(self) -> None:
        with self.session_factory() as session:
            running = list(
                session.scalars(select(Job).where(Job.status == "running")).all()
            )
            for job in running:
                job.status = "queued"
            session.commit()
            queued = list(
                session.scalars(
                    select(Job).where(Job.status == "queued").order_by(Job.id)
                ).all()
            )
        for job in queued:
            self._queue.put_nowait(job.id)
        for index in range(self.workers):
            self._tasks.append(asyncio.create_task(self._worker(index), name=f"job-worker-{index}"))

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()

    def enqueue(self, kind: str, payload: dict[str, Any]) -> Job:
        if kind not in self._semaphores:
            raise ValueError(f"unknown job type: {kind}")
        with self.session_factory() as session:
            job = Job(type=kind, status="queued", payload_json=payload)
            session.add(job)
            session.commit()
            session.refresh(job)
            self._queue.put_nowait(job.id)
            return job

    def cancel(self, job_id: int) -> None:
        self._cancelled.add(job_id)
        with self.session_factory() as session:
            job = session.get(Job, job_id)
            if job is not None and job.status in {"queued", "running"}:
                job.status = "cancelled"
                job.finished_at = datetime.now(timezone.utc)
                session.commit()

    def is_cancelled(self, job_id: int) -> bool:
        if job_id in self._cancelled:
            return True
        with self.session_factory() as session:
            job = session.get(Job, job_id)
            return job is not None and job.status == "cancelled"

    async def _worker(self, index: int) -> None:
        while True:
            job_id = await self._queue.get()
            try:
                await self._run(job_id)
            except asyncio.CancelledError:
                raise
            except Exception:  # pragma: no cover - defensive
                self._mark_failed(job_id, "worker crashed")
            finally:
                self._queue.task_done()

    async def _run(self, job_id: int) -> None:
        with self.session_factory() as session:
            job = session.get(Job, job_id)
            if job is None or job.status not in {"queued", "running"}:
                return
            job.status = "running"
            job.started_at = datetime.now(timezone.utc)
            session.commit()

        semaphore = self._semaphores[job.type]
        async with semaphore:
            try:
                with self.session_factory() as session:
                    result = await self._dispatch(session, job_id, job.type, job.payload_json or {})
                self._finish(job_id, result)
            except Exception as exc:
                self._mark_failed(job_id, f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}")

    async def _dispatch(
        self,
        session: Session,
        job_id: int,
        kind: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        def progress(done: int, total: int, message: str) -> None:
            job = session.get(Job, job_id)
            if job is not None:
                job.done = done
                job.total = total
                job.progress = round(done / total, 4) if total else 0.0
                job.result_json = {**(job.result_json or {}), "message": message}
                session.commit()

        if kind == "scan":
            root = session.get(LibraryRoot, int(payload.get("root_id", 0)))
            if root is None:
                raise ValueError("root not found")
            result = await asyncio.to_thread(
                scan_root, session, root, progress, force=bool(payload.get("force"))
            )
            return {
                "albums": result.albums,
                "files": result.files,
                "parsed_files": result.parsed_files,
            }
        if kind == "match":
            album_id = int(payload.get("album_id", 0))
            rows = await match_album(session, album_id, self.client)
            return {"candidates": len(rows)}
        if kind == "apply":
            plan_id = int(payload.get("plan_id", 0))
            return await apply_plan(
                session,
                plan_id,
                self.client,
                progress,
                lambda: self.is_cancelled(job_id),
            )
        if kind == "rollback":
            batch_id = str(payload.get("batch_id") or "")
            if not batch_id:
                raise ValueError("batch_id required")
            return await asyncio.to_thread(restore_batch, session, batch_id, progress)
        raise ValueError(f"unsupported job type: {kind}")

    def _finish(self, job_id: int, result: dict[str, Any]) -> None:
        with self.session_factory() as session:
            job = session.get(Job, job_id)
            if job is None:
                return
            if job.status == "cancelled":
                return
            job.status = "succeeded"
            job.progress = 1.0
            job.done = job.total
            job.result_json = result
            job.finished_at = datetime.now(timezone.utc)
            session.commit()

    def _mark_failed(self, job_id: int, error: str) -> None:
        with self.session_factory() as session:
            job = session.get(Job, job_id)
            if job is None:
                return
            if job.status == "cancelled":
                return
            job.status = "failed"
            job.error = error
            job.finished_at = datetime.now(timezone.utc)
            session.commit()


_runner: JobRunner | None = None


def set_runner(runner: JobRunner | None) -> None:
    global _runner
    _runner = runner


def get_runner() -> JobRunner:
    if _runner is None:
        raise RuntimeError("job runner is not started")
    return _runner

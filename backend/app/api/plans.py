from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import ChangePlan
from ..jobs.runner import get_runner
from ..schemas import ApplyPlanRequest, PlanItemsPatch
from ..services.plan import approve_plan, patch_items, plan_payload
from .deps import get_db

router = APIRouter()


@router.get("/plans/{plan_id}")
def get_plan(plan_id: int, session: Session = Depends(get_db)) -> dict[str, object]:
    plan = session.get(ChangePlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="plan not found")
    return plan_payload(plan)


@router.patch("/plans/{plan_id}/items")
def update_plan_items(
    plan_id: int, payload: PlanItemsPatch, session: Session = Depends(get_db)
) -> dict[str, object]:
    try:
        plan = patch_items(session, plan_id, [item.model_dump() for item in payload.items])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return plan_payload(plan)


@router.post("/plans/{plan_id}/apply")
def apply_plan(
    plan_id: int,
    payload: ApplyPlanRequest,
    session: Session = Depends(get_db),
) -> dict[str, object]:
    plan = session.get(ChangePlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="plan not found")
    if plan.status in {"applied", "reverted"}:
        raise HTTPException(status_code=409, detail="plan is already finalized")
    if payload.cover_url:
        plan.payload_json = {**(plan.payload_json or {}), "cover_url": payload.cover_url}
    approve_plan(session, plan_id)
    job = get_runner().enqueue("apply", {"plan_id": plan_id})
    return {"job_id": job.id, "status": job.status, "plan_id": plan_id}


@router.get("/albums/{album_id}/plans")
def album_plans(
    album_id: int, session: Session = Depends(get_db)
) -> list[dict[str, object]]:
    plans = session.scalars(
        select(ChangePlan)
        .where(ChangePlan.album_id == album_id)
        .order_by(ChangePlan.id.desc())
    ).all()
    return [
        {
            "id": plan.id,
            "status": plan.status,
            "policy": plan.policy,
            "created_at": plan.created_at.isoformat() if plan.created_at else None,
        }
        for plan in plans
    ]

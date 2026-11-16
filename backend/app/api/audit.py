from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import AuditLog
from .deps import get_db, serialize_audit

router = APIRouter()


@router.get("/audit-logs")
def list_audit_logs(
    limit: int = 100, session: Session = Depends(get_db)
) -> list[dict[str, object]]:
    rows = session.scalars(
        select(AuditLog).order_by(AuditLog.id.desc()).limit(min(limit, 500))
    ).all()
    return [serialize_audit(row) for row in rows]

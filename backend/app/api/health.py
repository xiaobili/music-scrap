from __future__ import annotations

import os
import shutil

from fastapi import APIRouter
from sqlalchemy import text

from ..core.config import get_settings
from ..db.session import get_engine

router = APIRouter()


@router.get("/health")
def health() -> dict[str, object]:
    db_ok = False
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    roots = get_settings().roots
    roots_ok = all(root.exists() and os.access(root, os.R_OK) for root in roots) if roots else True
    fpcalc_ok = shutil.which("fpcalc") is not None
    ok = db_ok and roots_ok and fpcalc_ok
    return {
        "status": "ok" if ok else "degraded",
        "db": db_ok,
        "fpcalc": fpcalc_ok,
        "roots_readable": roots_ok,
    }

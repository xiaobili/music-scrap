from __future__ import annotations

import shutil

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..core.security import mask
from ..db.session import get_engine
from ..schemas import SettingsUpdate
from ..services.settings import DEFAULTS, SECRET_KEYS, SettingsStore
from .deps import get_db

router = APIRouter()


def _public(session: Session) -> dict[str, object]:
    store = SettingsStore(session)
    values = store.as_dict()
    public = {key: value for key, value in values.items() if key not in SECRET_KEYS}
    masked = {key: mask(str(values.get(key) or "")) for key in SECRET_KEYS}
    return {
        "values": public,
        "masked": masked,
        "providers": store.provider_states(_unofficial_enabled()),
        "system": {
            "fpcalc": shutil.which("fpcalc") is not None,
            "version": "0.1.0",
            "db": str(get_engine().url),
        },
    }


def _unofficial_enabled() -> bool:
    from ..core.config import get_settings

    return get_settings().enable_unofficial_providers


@router.get("/settings")
def get_settings_api(session: Session = Depends(get_db)) -> dict[str, object]:
    return _public(session)


@router.put("/settings")
def update_settings_api(
    payload: SettingsUpdate, session: Session = Depends(get_db)
) -> dict[str, object]:
    store = SettingsStore(session)
    for key, value in payload.values.items():
        if key not in DEFAULTS:
            continue
        if key in SECRET_KEYS and isinstance(value, str) and "•" in value:
            continue
        store.set(key, value)
    return _public(session)

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from ..core.security import decrypt, encrypt, mask
from ..db.models import AppSetting

DEFAULTS: dict[str, Any] = {
    "field_policy": "fill_only",
    "cover_policy": "if_missing",
    "safe_mode": False,
    "musicbrainz.enabled": True,
    "acoustid.apikey": "",
    "discogs.token": "",
    "spotify.client_id": "",
    "spotify.client_secret": "",
    "netease.enabled": False,
    "netease.cookie": "",
}

SECRET_KEYS = {
    "acoustid.apikey",
    "discogs.token",
    "spotify.client_secret",
    "netease.cookie",
}

PROVIDERS: list[dict[str, Any]] = [
    {
        "id": "musicbrainz",
        "label": "MusicBrainz",
        "rate": "1 req/s",
        "credential_keys": [],
        "requires": [],
    },
    {
        "id": "acoustid",
        "label": "AcoustID",
        "rate": "3 req/s",
        "credential_keys": ["acoustid.apikey"],
        "requires": ["acoustid.apikey"],
    },
    {
        "id": "discogs",
        "label": "Discogs",
        "rate": "60 req/min",
        "credential_keys": ["discogs.token"],
        "requires": ["discogs.token"],
    },
    {
        "id": "spotify",
        "label": "Spotify",
        "rate": "429 自动退避",
        "credential_keys": ["spotify.client_id", "spotify.client_secret"],
        "requires": ["spotify.client_id", "spotify.client_secret"],
    },
    {
        "id": "netease",
        "label": "网易云 / QQ 音乐",
        "rate": "0.5 req/s",
        "credential_keys": ["netease.cookie"],
        "requires": [],
    },
]


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _load(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


class SettingsStore:
    def __init__(self, session: Session):
        self.session = session

    def get(self, key: str, default: Any = None) -> Any:
        row = self.session.get(AppSetting, key)
        if row is None:
            return DEFAULTS.get(key, default)
        try:
            return _load(decrypt(row.value_encrypted))
        except ValueError:
            return DEFAULTS.get(key, default)

    def set(self, key: str, value: Any) -> None:
        row = self.session.get(AppSetting, key)
        encrypted = encrypt(_dump(value))
        if row is None:
            row = AppSetting(key=key, value_encrypted=encrypted, is_secret=key in SECRET_KEYS)
            self.session.add(row)
        else:
            row.value_encrypted = encrypted
            row.is_secret = key in SECRET_KEYS
        self.session.commit()

    def as_dict(self) -> dict[str, Any]:
        values = dict(DEFAULTS)
        for row in self.session.query(AppSetting).all():
            try:
                values[row.key] = _load(decrypt(row.value_encrypted))
            except ValueError:
                continue
        return values

    def provider_states(self, enable_unofficial: bool) -> list[dict[str, Any]]:
        values = self.as_dict()
        result: list[dict[str, Any]] = []
        for provider in PROVIDERS:
            requires = provider["requires"]
            configured = all(bool(values.get(key)) for key in requires) if requires else True
            if provider["id"] == "netease":
                enabled = bool(values.get("netease.enabled")) and enable_unofficial
            else:
                enabled = bool(values.get(f"{provider['id']}.enabled", True))
            masked: dict[str, str] = {}
            for key in provider["credential_keys"]:
                secret = str(values.get(key) or "")
                masked[key] = mask(secret) if secret else ""
            result.append(
                {
                    "id": provider["id"],
                    "label": provider["label"],
                    "rate": provider["rate"],
                    "enabled": enabled and configured,
                    "configured": configured,
                    "enabled_by_user": enabled,
                    "masked": masked,
                }
            )
        return result

    def update(self, payload: dict[str, Any]) -> None:
        for key, value in payload.items():
            if key not in DEFAULTS:
                continue
            self.set(key, value)

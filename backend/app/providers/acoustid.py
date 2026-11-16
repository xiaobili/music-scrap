from __future__ import annotations

import asyncio
import json
import subprocess
from typing import Any

from .base import Capability, Provider, ProviderError

FPCALC = "fpcalc"


def fingerprint_file(path: str, length: int = 120) -> tuple[str, float]:
    try:
        output = subprocess.run(
            [FPCALC, "-json", "-length", str(length), path],
            capture_output=True,
            check=True,
            timeout=60,
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProviderError(f"fpcalc failed: {exc}") from exc
    data = json.loads(output.decode("utf-8"))
    return data["fingerprint"], float(data.get("duration") or 0)


class AcoustIDProvider(Provider):
    name = "acoustid"
    capabilities = {Capability.FINGERPRINT}
    rate = 3.0

    async def is_enabled(self) -> bool:
        if not self.ctx.store.get("acoustid.enabled", True):
            return False
        return bool(self.ctx.store.get("acoustid.apikey"))

    async def lookup(self, path: str) -> list[dict[str, Any]]:
        api_key = self.ctx.store.get("acoustid.apikey")
        if not api_key:
            return []
        fingerprint, duration = await asyncio.to_thread(fingerprint_file, path)
        cache_key = self._cache_key("lookup", fingerprint, str(int(duration)))
        from .base import cached

        payload = await cached(
            self.ctx.session,
            self.name,
            cache_key,
            90 * 24 * 3600,
            lambda: self._lookup(api_key, fingerprint, duration),
        )
        return payload.get("results", [])

    async def _lookup(
        self, api_key: str, fingerprint: str, duration: float
    ) -> dict[str, Any]:
        await self.bucket.acquire()
        response = await self.ctx.client.post(
            "https://api.acoustid.org/v2/lookup",
            data={
                "client": api_key,
                "meta": "recordings releasegroups compress",
                "duration": int(duration),
                "fingerprint": fingerprint,
            },
        )
        if response.status_code != 200:
            raise ProviderError(f"AcoustID HTTP {response.status_code}")
        return response.json()

    async def lookup_release_groups(self, path: str) -> list[str]:
        try:
            results = await self.lookup(path)
        except ProviderError:
            return []
        groups: list[str] = []
        for result in results:
            for recording in result.get("recordings", []) or []:
                for group in recording.get("releasegroups", []) or []:
                    group_id = group.get("id")
                    if group_id:
                        groups.append(group_id)
        return groups

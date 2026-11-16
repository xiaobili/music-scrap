from __future__ import annotations

from .acoustid import AcoustIDProvider
from .base import Provider, ProviderContext
from .discogs import DiscogsProvider
from .musicbrainz import MusicBrainzProvider
from .netease import NeteaseProvider
from .spotify import SpotifyProvider

PROVIDER_CLASSES = [
    MusicBrainzProvider,
    AcoustIDProvider,
    DiscogsProvider,
    SpotifyProvider,
    NeteaseProvider,
]


class ProviderRegistry:
    def __init__(self, ctx: ProviderContext):
        self.ctx = ctx
        self.providers: dict[str, Provider] = {
            provider_cls.name: provider_cls(ctx) for provider_cls in PROVIDER_CLASSES
        }

    def get(self, name: str) -> Provider | None:
        return self.providers.get(name)

    async def enabled(self) -> list[Provider]:
        active: list[Provider] = []
        for provider in self.providers.values():
            try:
                if await provider.is_enabled():
                    active.append(provider)
            except Exception:
                continue
        return active

from __future__ import annotations

import httpx
import pytest
import respx

from app.core.config import get_settings
from app.providers.base import ProviderContext, ReleaseQuery
from app.providers.qq import QQProvider
from app.services.settings import SettingsStore

SEARCH_PAYLOAD = {
    "code": 0,
    "data": {
        "song": {
            "list": [
                {"album": {"mid": "000MkMni19ClKG", "name": "叶惠美"}},
                {"album": {"mid": "000MkMni19ClKG", "name": "叶惠美"}},
                {"album": {"mid": "000MkMni19ClKG", "name": "叶惠美"}},
            ]
        }
    },
}

ALBUM_PAYLOAD = {
    "code": 0,
    "data": {
        "mid": "000MkMni19ClKG",
        "id": 8220,
        "name": "叶惠美",
        "aDate": "2003-07-31",
        "company": "杰威尔音乐有限公司",
        "genre": "Pop 流行",
        "singername": "周杰伦",
        "list": [
            {
                "songname": "以父之名",
                "belongCD": 1,
                "cdIdx": 0,
                "interval": 342,
                "singer": [{"name": "周杰伦"}],
            },
            {
                "songname": "懦夫",
                "belongCD": 2,
                "cdIdx": 4,
                "interval": 218,
                "singer": [{"name": "周杰伦"}, {"name": "黑龙"}],
            },
        ],
    },
}


@pytest.fixture
def provider(db) -> QQProvider:
    store = SettingsStore(db)
    store.set("qq.enabled", True)
    return QQProvider(ProviderContext(db, httpx.AsyncClient(), store))


def enable_unofficial(monkeypatch, value: bool) -> None:
    monkeypatch.setenv("ENABLE_UNOFFICIAL_PROVIDERS", "true" if value else "false")
    get_settings.cache_clear()


def test_headers_omit_cookie_when_not_configured(provider: QQProvider) -> None:
    headers = provider._headers()

    assert headers["Referer"] == "https://y.qq.com/"
    assert "Cookie" not in headers


def test_headers_include_configured_cookie(provider: QQProvider) -> None:
    provider.ctx.store.set("qq.cookie", "uin=12345; qqmusic_key=secret")

    headers = provider._headers()

    assert headers["Cookie"] == "uin=12345; qqmusic_key=secret"


async def test_disabled_when_unofficial_flag_is_off(provider: QQProvider, monkeypatch) -> None:
    enable_unofficial(monkeypatch, False)

    assert await provider.is_enabled() is False


async def test_enabled_when_flag_and_setting_are_on(provider: QQProvider, monkeypatch) -> None:
    enable_unofficial(monkeypatch, True)

    assert await provider.is_enabled() is True


async def test_disabled_when_setting_is_off(provider: QQProvider, monkeypatch) -> None:
    enable_unofficial(monkeypatch, True)
    provider.ctx.store.set("qq.enabled", False)

    assert await provider.is_enabled() is False


def test_parse_album_payload(provider: QQProvider) -> None:
    release = provider._parse(ALBUM_PAYLOAD)

    assert release is not None
    assert release.provider == "qq"
    assert release.provider_id == "000MkMni19ClKG"
    assert release.title == "叶惠美"
    assert release.artist == "周杰伦"
    assert release.year == 2003
    assert release.label == "杰威尔音乐有限公司"
    assert release.genres == ["Pop 流行"]
    assert len(release.tracks) == 2
    assert release.tracks[0].disc == 1
    assert release.tracks[0].position == 1
    assert release.tracks[0].title == "以父之名"
    assert release.tracks[0].artist == "周杰伦"
    assert release.tracks[0].duration_ms == 342000
    assert release.tracks[1].disc == 2
    assert release.tracks[1].position == 5
    assert release.tracks[1].artist == "周杰伦, 黑龙"
    assert release.tracks[1].duration_ms == 218000
    assert [cover.url for cover in release.covers] == [
        "https://y.gtimg.cn/music/photo_new/T002R500x500M000000MkMni19ClKG.jpg"
    ]


async def test_get_covers_returns_release_covers(provider: QQProvider) -> None:
    release = provider._parse(ALBUM_PAYLOAD)
    assert release is not None

    covers = await provider.get_covers(release)

    assert covers == release.covers


@respx.mock
async def test_search_release_dedupes_album_mids(provider: QQProvider, monkeypatch) -> None:
    enable_unofficial(monkeypatch, True)
    search_route = respx.get("https://c.y.qq.com/soso/fcgi-bin/client_search_cp").mock(
        return_value=httpx.Response(200, json=SEARCH_PAYLOAD)
    )
    album_route = respx.get("https://c.y.qq.com/v8/fcg-bin/fcg_v8_album_info_cp.fcg").mock(
        return_value=httpx.Response(200, json=ALBUM_PAYLOAD)
    )

    releases = await provider.search_release(ReleaseQuery(artist="周杰伦", album="叶惠美"))

    assert search_route.called
    assert album_route.call_count == 1
    assert len(releases) == 1
    assert releases[0].provider_id == "000MkMni19ClKG"

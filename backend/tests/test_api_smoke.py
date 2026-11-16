from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import tagio
from app.db.models import Album, ChangePlan, LibraryRoot, MatchCandidate
from app.db.session import get_session_factory
from app.main import app
from app.providers.base import CanonicalRelease, CanonicalTrack

from .conftest import make_audio


def _seed_library(library: Path) -> None:
    directory = library / "甜梅号" / "城市天气 (2010)"
    directory.mkdir(parents=True, exist_ok=True)
    for index, title in enumerate(["一个人的旅行", "城市天气"], start=1):
        path = make_audio(directory / f"0{index} - {title}.flac")
        tagio.write(
            path,
            {
                "ALBUM": "城市天气",
                "ALBUMARTIST": "甜梅号",
                "ARTIST": "甜梅号",
                "TITLE": title,
                "TRACKNUMBER": str(index),
                "TRACKTOTAL": "2",
            },
        )


@pytest.fixture
def client(settings, library):
    _seed_library(library)
    with TestClient(app) as test_client:
        yield test_client


def _wait_job(client: TestClient, job_id: int, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] in {"succeeded", "failed", "cancelled"}:
            return payload
        time.sleep(0.2)
    raise AssertionError("job did not finish in time")


def test_health_ok(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_auth_error_shape(client):
    response = client.get("/api/albums/9999")
    assert response.status_code == 404
    body = response.json()
    assert set(body) == {"code", "message", "details", "trace_id"}


def _create_root_and_scan(client, library) -> int:
    created = client.post("/api/roots", json={"path": str(library)})
    assert created.status_code == 201, created.text
    root_id = created.json()["id"]
    scan = client.post(f"/api/roots/{root_id}/scan")
    assert scan.status_code == 200, scan.text
    job = _wait_job(client, scan.json()["job_id"])
    assert job["status"] == "succeeded", job
    return root_id


def test_scan_and_album_list(client, library):
    _create_root_and_scan(client, library)
    albums = client.get("/api/albums").json()
    assert albums["total"] == 1
    album = albums["items"][0]
    assert album["title"] == "城市天气"
    assert album["kind"] == "split"
    detail = client.get(f"/api/albums/{album['id']}").json()
    assert len(detail["tracks"]) == 2
    assert detail["tags"]["TITLE"] == ["一个人的旅行"]


def test_job_sse_emits_done(client, library):
    created = client.post("/api/roots", json={"path": str(library)})
    root_id = created.json()["id"]
    job_id = client.post(f"/api/roots/{root_id}/scan").json()["job_id"]
    _wait_job(client, job_id)
    with client.stream("GET", f"/api/jobs/{job_id}/events") as response:
        body = "".join(response.iter_text())
    assert "event: done" in body


def test_settings_masks_secrets(client):
    updated = client.put(
        "/api/settings", json={"values": {"discogs.token": "tok_secret_123"}}
    )
    assert updated.status_code == 200
    payload = updated.json()
    assert "tok_secret_123" not in updated.text
    assert payload["masked"]["discogs.token"].startswith("tok")
    provider = next(p for p in payload["providers"] if p["id"] == "discogs")
    assert provider["configured"] is True


def test_rejects_root_that_is_a_file(client, library):
    file_path = library / "not-a-dir.txt"
    file_path.write_text("x")
    response = client.post("/api/roots", json={"path": str(file_path)})
    assert response.status_code == 400


def _seed_candidate(album_id: int) -> int:
    release = CanonicalRelease(
        provider="musicbrainz",
        provider_id="mb-1",
        title="城市天气",
        artist="甜梅号",
        year=2010,
        label="小白兔唱片",
        catalog_number="RB-045",
        release_mbid="mb-1",
        tracks=[
            CanonicalTrack(position=1, title="一个人的旅行", duration_ms=3000),
            CanonicalTrack(position=2, title="城市天气", duration_ms=3000),
        ],
    )
    with get_session_factory()() as session:
        candidate = MatchCandidate(
            album_id=album_id,
            provider="musicbrainz",
            provider_id="mb-1",
            score=0.9,
            payload_json=release.model_dump(mode="json"),
            raw_score_json={},
        )
        session.add(candidate)
        session.commit()
        return candidate.id


def test_select_plan_apply_and_rollback(client, library):
    _create_root_and_scan(client, library)
    album = client.get("/api/albums").json()["items"][0]
    candidate_id = _seed_candidate(album["id"])

    selected = client.post(
        f"/api/albums/{album['id']}/select",
        json={"candidate_id": candidate_id, "policy": "fill_only"},
    )
    assert selected.status_code == 200, selected.text
    plan = selected.json()
    assert plan["items"]
    plan_id = plan["id"]

    patched = client.patch(
        f"/api/plans/{plan_id}/items",
        json={"items": [{"id": plan["items"][-1]["id"], "selected": False}]},
    )
    assert patched.status_code == 200
    assert patched.json()["selected_count"] == plan["selected_count"] - 1

    applied = client.post(f"/api/plans/{plan_id}/apply", json={})
    assert applied.status_code == 200, applied.text
    job = _wait_job(client, applied.json()["job_id"])
    assert job["status"] == "succeeded", job

    first = next((library / "甜梅号" / "城市天气 (2010)").glob("01 - *.flac"))
    tags = tagio.read(first)
    assert tags["ALBUMARTIST"] == ["甜梅号"]
    assert tags["LABEL"] == ["小白兔唱片"]

    batches = client.get("/api/backups").json()
    assert batches and batches[0]["files"] == 2
    restored = client.post(f"/api/backups/{batches[0]['batch_id']}/restore")
    assert restored.status_code == 200
    rollback_job = _wait_job(client, restored.json()["job_id"])
    assert rollback_job["status"] == "succeeded", rollback_job
    tags = tagio.read(first)
    assert "LABEL" not in tags


def test_select_plan_uses_saved_field_policy(client, library):
    _create_root_and_scan(client, library)
    album = client.get("/api/albums").json()["items"][0]
    candidate_id = _seed_candidate(album["id"])
    updated = client.put("/api/settings", json={"values": {"field_policy": "overwrite"}})
    assert updated.status_code == 200

    selected = client.post(
        f"/api/albums/{album['id']}/select",
        json={"candidate_id": candidate_id},
    )

    assert selected.status_code == 200, selected.text
    assert selected.json()["policy"] == "overwrite"


def test_init_db_repairs_album_status(tmp_path):
    from app.db.session import get_session_factory, init_db

    db_path = tmp_path / "repair.db"
    init_db(db_path)
    with get_session_factory()() as session:
        root = LibraryRoot(path=str(tmp_path / "library"))
        session.add(root)
        session.commit()
        album = Album(root_id=root.id, rel_path="A/Album", status="unmatched")
        session.add(album)
        session.commit()
        session.add(ChangePlan(album_id=album.id, status="applied"))
        session.commit()
        album_id = album.id

    init_db(db_path)

    with get_session_factory()() as session:
        repaired = session.get(Album, album_id)
        assert repaired is not None
        assert repaired.status == "matched"

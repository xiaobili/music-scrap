from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import init_engine


def make_audio(path: Path, *, seconds: float = 2.0, frequency: int = 440) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    codec = {
        ".flac": ["-c:a", "flac"],
        ".mp3": ["-c:a", "libmp3lame", "-b:a", "128k"],
        ".m4a": ["-c:a", "aac", "-b:a", "128k"],
        ".wav": ["-c:a", "pcm_s16le"],
    }[path.suffix.lower()]
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={frequency}:duration={seconds}",
            *codec,
            str(path),
        ],
        check=True,
    )
    return path


def make_silence(path: Path, *, seconds: float = 901.0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=r=8000:cl=mono:d={seconds}",
            "-c:a",
            "flac",
            str(path),
        ],
        check=True,
    )
    return path


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setenv("MUSIC_ROOTS", str(tmp_path / "library"))
    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


@pytest.fixture
def db(tmp_path):
    engine = init_engine(tmp_path / "unit.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with factory() as session:
        yield session
    engine.dispose()


@pytest.fixture
def library(tmp_path) -> Path:
    root = tmp_path / "library"
    root.mkdir(parents=True, exist_ok=True)
    return root

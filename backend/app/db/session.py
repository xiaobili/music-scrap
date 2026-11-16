from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import Engine, create_engine, event, select, update
from sqlalchemy.orm import Session, sessionmaker

from ..core.config import get_settings
from .base import Base
from .models import Album, ChangePlan

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def init_engine(db_path: Path | str | None = None) -> Engine:
    global _engine, _session_factory
    path = Path(db_path or get_settings().db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(
        f"sqlite:///{path}",
        future=True,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection, _record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    _engine = engine
    _session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    return engine


def get_engine() -> Engine:
    if _engine is None:
        init_engine()
    assert _engine is not None
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    if _session_factory is None:
        init_engine()
    assert _session_factory is not None
    return _session_factory


def _repair_album_status(engine: Engine) -> None:
    """修复历史数据：已生成变更计划的专辑说明已完成人工匹配，状态归位为 matched。"""
    with Session(engine) as session:
        session.execute(
            update(Album)
            .where(
                Album.status != "matched",
                Album.id.in_(select(ChangePlan.album_id)),
            )
            .values(status="matched")
        )
        session.commit()


def init_db(db_path: Path | str | None = None) -> None:
    engine = init_engine(db_path)
    Base.metadata.create_all(engine)
    _repair_album_status(engine)


def get_session() -> Iterator[Session]:
    factory = get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()

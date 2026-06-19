from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import URL, MetaData, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import settings

__all__ = ["Base", "get_engine", "get_session", "metadata"]

_engine_lock: threading.Lock = threading.Lock()
_engine: Engine | None = None
_session_lock: threading.Lock = threading.Lock()
_SessionLocal: sessionmaker | None = None

metadata = MetaData(
    naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)


class Base(DeclarativeBase):
    metadata = metadata


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is not None:
                return _engine
            db_url = URL.create(
                drivername="postgresql",
                username=settings.DB_USER,
                password=settings.DB_PASSWORD,
                host=settings.DB_HOST,
                port=settings.DB_PORT,
                database=settings.DB_NAME,
            )
            _engine = create_engine(
                db_url,
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,
                pool_recycle=3600,
                connect_args={
                    "connect_timeout": 5,
                    "application_name": "esim-ego-server",
                },
            )
    return _engine


def _get_sessionmaker() -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        with _session_lock:
            if _SessionLocal is not None:
                return _SessionLocal
            _SessionLocal = sessionmaker(
                bind=get_engine(),
                autocommit=False,
                autoflush=False,
            )
    return _SessionLocal


@contextmanager
def get_session() -> Generator[Session, None, None]:
    session: Session = _get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

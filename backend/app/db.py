"""Database engine, session and tables (SQLite by default, Postgres via DATABASE_URL)."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from sqlalchemy import JSON, Boolean, Column, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator

from .config import settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Stores UTC; always returns timezone-aware UTC datetimes (SQLite drops tz info otherwise)."""
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        value = value.astimezone(timezone.utc)
        return value.replace(tzinfo=None) if dialect.name == "sqlite" else value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


_engine_kwargs = {"pool_pre_ping": True}
if settings.is_sqlite:
    _engine_kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}

engine = create_engine(settings.database_url, **_engine_kwargs)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    """A customer account. The key is both the web login and the desktop license key."""
    __tablename__ = "app_users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    identifier = Column(String(255), unique=True, nullable=False, index=True)
    api_key_hash = Column(String(64), unique=True, nullable=False, index=True)
    api_key_prefix = Column(String(12), nullable=False, default="")
    key_start_date = Column(UTCDateTime(), nullable=False, default=utcnow)
    key_end_date = Column(UTCDateTime(), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    role = Column(String(20), nullable=False, default="user")  # user | admin
    plan = Column(String(50), nullable=False, default="pro")
    max_devices = Column(Integer, nullable=False, default=2)
    devices = Column(JSON, nullable=False, default=list)
    notes = Column(Text)
    created_at = Column(UTCDateTime(), default=utcnow, nullable=False)
    updated_at = Column(UTCDateTime(), default=utcnow, onupdate=utcnow)


class Job(Base):
    """Long-running work (pick runs, results refresh, simulations) with progress and ETA."""
    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True)
    kind = Column(String(30), nullable=False)
    league = Column(String(8))
    status = Column(String(20), nullable=False, default="queued")
    progress = Column(Float, default=0.0)
    eta_seconds = Column(Float)
    message = Column(Text, default="")
    params = Column(JSON, default=dict)
    result = Column(JSON)
    created_at = Column(UTCDateTime(), default=utcnow)
    started_at = Column(UTCDateTime())
    finished_at = Column(UTCDateTime())


class LogEntry(Base):
    __tablename__ = "log_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(UTCDateTime(), default=utcnow, index=True)
    level = Column(String(10), index=True)
    source = Column(String(60))
    message = Column(Text)


def init_db() -> None:
    Base.metadata.create_all(engine)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

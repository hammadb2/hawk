"""SQLAlchemy engine, session, and base. SQLite (dev) / PostgreSQL (prod)."""
from __future__ import annotations

import logging
import threading

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from config import DATABASE_URL, CONNECT_ARGS

logger = logging.getLogger(__name__)

engine = create_engine(DATABASE_URL, connect_args=CONNECT_ARGS)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

_schema_lock = threading.Lock()
_schema_ready = False


def _ensure_schema_once() -> None:
    """Create tables on first ORM use — avoids blocking app bind on Railway (healthchecks hit /health before DB)."""
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        try:
            init_db()
        except Exception:
            logger.exception("init_db failed — DB routes may error until DATABASE_URL is valid")
        _schema_ready = True


def get_db():
    _ensure_schema_once()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables. Call on startup."""
    from models import (  # noqa: F401
        User,
        Domain,
        Scan,
        Notification,
        Report,
        IgnoredFinding,
        AgencyClient,
        HawkMessage,
        PasswordResetToken,
    )
    Base.metadata.create_all(bind=engine)

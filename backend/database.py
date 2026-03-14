"""SQLAlchemy engine, session, and base. SQLite (dev) / PostgreSQL (prod)."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from backend.config import DATABASE_URL, CONNECT_ARGS

engine = create_engine(DATABASE_URL, connect_args=CONNECT_ARGS)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables. Call on startup."""
    from backend.models import (  # noqa: F401
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

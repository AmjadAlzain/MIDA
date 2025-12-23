"""Database session management."""

from collections.abc import Generator
from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker[Session]] = None


def get_engine() -> Optional[Engine]:
    """
    Get or create the SQLAlchemy engine.
    Returns None if DATABASE_URL is not configured.
    """
    global _engine
    settings = get_settings()

    if not settings.database_url:
        return None

    if _engine is None:
        _engine = create_engine(
            settings.database_url,
            pool_pre_ping=True,
        )
    return _engine


def get_session_factory() -> Optional[sessionmaker[Session]]:
    """Get or create the session factory."""
    global _SessionLocal
    engine = get_engine()

    if engine is None:
        return None

    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a database session.
    Usage: db: Session = Depends(get_db)
    """
    session_factory = get_session_factory()
    if session_factory is None:
        raise RuntimeError("Database not configured. Set DATABASE_URL environment variable.")

    db = session_factory()
    try:
        yield db
    finally:
        db.close()


def check_db_connection() -> tuple[bool, Optional[str]]:
    """
    Check database connectivity.
    Returns (success, error_message).
    """
    engine = get_engine()
    if engine is None:
        return False, "unconfigured"

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            conn.commit()
        return True, None
    except Exception:
        # Never leak connection details
        return False, "connection_failed"

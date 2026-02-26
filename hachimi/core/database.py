"""SQLite database engine and session management via SQLModel."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Generator

from sqlmodel import Session, SQLModel, create_engine

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_DB_PATH = _PROJECT_ROOT / "data" / "hachimi.db"

_engine = None


def get_engine(db_path: Path | str | None = None):
    """Get or create the SQLAlchemy engine (singleton)."""
    global _engine
    if _engine is None:
        db_path = Path(db_path) if db_path else _DEFAULT_DB_PATH
        db_path.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{db_path}"
        _engine = create_engine(
            url,
            echo=False,
            connect_args={"check_same_thread": False},  # needed for multi-thread FastAPI
        )
        logger.info("Database engine created: %s", db_path)
    return _engine


def create_db_and_tables(db_path: Path | str | None = None):
    """Create all tables defined by SQLModel metadata."""
    engine = get_engine(db_path)
    SQLModel.metadata.create_all(engine)
    logger.info("Database tables created / verified.")


def get_session() -> Generator[Session, None, None]:
    """Yield a database session (for FastAPI Depends or manual use)."""
    engine = get_engine()
    with Session(engine) as session:
        yield session


def reset_engine():
    """Reset the engine singleton (for testing)."""
    global _engine
    if _engine:
        _engine.dispose()
    _engine = None

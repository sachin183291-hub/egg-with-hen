"""
Database session management.
Supports PostgreSQL (primary) and SQLite (dev fallback).
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

from app.config import settings
from app.database.models import Base

import os
from pathlib import Path

# Fix relative SQLite paths to always resolve to the backend directory
# regardless of where uvicorn is started from.
db_url = settings.DATABASE_URL
if db_url.startswith("sqlite:///./"):
    db_name = db_url.replace("sqlite:///./", "")
    backend_dir = Path(__file__).resolve().parent.parent.parent
    db_url = f"sqlite:///{backend_dir / db_name}"

# Create engine with appropriate settings per DB type
if db_url.startswith("sqlite"):
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
        echo=settings.DEBUG,
    )
else:
    engine = create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        echo=settings.DEBUG,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def create_tables():
    """Create all tables (use Alembic for production migrations)."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that provides a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

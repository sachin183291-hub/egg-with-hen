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

# Fix for Render: SQLAlchemy 1.4+ requires postgresql:// instead of postgres://
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

# Create engine with appropriate settings per DB type
if db_url.startswith("sqlite"):
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
        echo=settings.DEBUG,
    )
else:
    engine = create_engine(
        db_url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        echo=settings.DEBUG,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


import time
import sqlalchemy

def create_tables():
    """Create all tables (use Alembic for production migrations)."""
    global engine, SessionLocal
    retries = 5
    for i in range(retries):
        try:
            Base.metadata.create_all(bind=engine)
            print("[OK] Database tables created successfully.")
            break
        except Exception as e:
            if i < retries - 1:
                print(f"[WARNING] Database not ready yet, retrying in 3 seconds... ({i+1}/{retries})")
                time.sleep(3)
            else:
                print(f"[WARNING] Primary database unavailable ({e}). Falling back to local SQLite to keep server operational.")
                try:
                    backend_dir = Path(__file__).resolve().parent.parent.parent
                    fallback_url = f"sqlite:///{backend_dir / 'giotag.db'}"
                    engine = create_engine(fallback_url, connect_args={"check_same_thread": False})
                    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
                    Base.metadata.create_all(bind=engine)
                    print("[OK] Local SQLite fallback database initialized.")
                except Exception as ex:
                    print(f"[ERROR] SQLite fallback error: {ex}")


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that provides a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

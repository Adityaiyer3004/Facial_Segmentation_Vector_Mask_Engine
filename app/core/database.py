from __future__ import annotations

import os
from datetime import datetime
from typing import Generator

from sqlalchemy import Column, DateTime, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# --- DB URL ---
# Default to local SQLite so it "just works" if DATABASE_URL isn't set.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")

# For SQLite we need a special connect arg
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class ProcessedImage(Base):
    """
    Simple cache table:
      cache_key -> SVG result
    """
    __tablename__ = "processed_images"

    cache_key = Column(String(64), primary_key=True, index=True)
    svg_result = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


def get_db() -> Generator:
    """
    FastAPI dependency to get a DB session.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """
    Create tables if they don't exist.
    Call this once on startup.
    """
    Base.metadata.create_all(bind=engine)

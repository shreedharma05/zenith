"""Database engine/session for the web backend (SQLite by default; swap
DATABASE_URL to Postgres for real production deployments)."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from . import config

_connect_args = {"check_same_thread": False} if config.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(
    config.DATABASE_URL,
    connect_args=_connect_args,
    # Neon (and most serverless/pooled Postgres) silently closes idle
    # connections; pre_ping validates a pooled connection before reuse and
    # transparently reconnects instead of raising "SSL connection has been
    # closed unexpectedly" on the next query. recycle bounds how long a
    # connection can sit in the pool before being proactively replaced.
    pool_pre_ping=True,
    pool_recycle=300,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

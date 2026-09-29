"""Database engine/session for the web backend (SQLite by default; swap
DATABASE_URL to Postgres for real production deployments)."""

from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
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


def ensure_schema() -> None:
    """Backfill columns added after the initial deploy onto an existing
    `users` table -- `Base.metadata.create_all` only creates missing tables,
    it never alters one that already exists (e.g. the live Neon database)."""
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("users")}
    with engine.begin() as conn:
        for column in ("google_sub", "linkedin_sub"):
            if column not in existing:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {column} VARCHAR(255)"))
            conn.execute(text(f"CREATE UNIQUE INDEX IF NOT EXISTS ix_users_{column} ON users ({column})"))

"""SQLAlchemy models for the web backend."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    # Provider's stable subject id once linked via "Sign in with Google/LinkedIn".
    # Password-only accounts leave these null; hashed_password still gets a
    # random, unusable value for OAuth-created accounts (see oauth_routes.py)
    # rather than making the column nullable, to avoid an ALTER COLUMN migration.
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    linkedin_sub: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)


class ResumeVersion(Base):
    __tablename__ = "resume_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    object_version_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

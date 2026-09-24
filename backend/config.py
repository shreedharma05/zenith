"""Settings for the web backend: auth, database, email, cookies, and R2.

Kept separate from `zenith/config.py` (which governs resume parsing / LLM /
job search, and is reusable independently of any particular frontend) since
these settings are web-auth specific.
"""

from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logger = logging.getLogger(__name__)

_DEFAULT_SECRET = "dev-insecure-secret-change-me"
# `or` (not a bare os.getenv default) because docker-compose's `${VAR:-}` sets
# an empty string rather than leaving the variable unset, which would
# otherwise silently defeat this fallback.
SECRET_KEY = os.getenv("AUTH_SECRET_KEY") or _DEFAULT_SECRET
if SECRET_KEY == _DEFAULT_SECRET:
    logger.warning(
        "AUTH_SECRET_KEY is not set -- using an insecure default. "
        "Set AUTH_SECRET_KEY in .env before deploying to production."
    )

ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", str(60 * 24 * 7)))
EMAIL_TOKEN_EXPIRE_MINUTES = int(os.getenv("EMAIL_TOKEN_EXPIRE_MINUTES", "60"))

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./zenith.db")

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").strip().lower() == "true"

# SMTP is optional in development: if SMTP_HOST is empty, emails are logged
# instead of sent so signup/verify/reset flows are still testable locally.
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "no-reply@zenith.local")

# Resume versions are managed by the application with unique object keys, so
# R2 bucket versioning is not required.
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID", "")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "")
R2_OBJECT_BUCKET = os.getenv("R2_OBJECT_BUCKET", "")
R2_ENDPOINT_URL = os.getenv("R2_ENDPOINT_URL", "")


def generate_dev_secret() -> str:
    """Helper for `.env.example` guidance -- not called automatically."""
    return secrets.token_hex(32)

"""\"Sign in with Google/LinkedIn\" via OAuth2 + OpenID Connect.

The redirect_uri registered with each provider always points at the
*frontend's* domain (proxied through Next.js to this backend) rather than
this service's own domain -- so the Set-Cookie this callback issues rides
back through the same-origin proxy and lands as a first-party cookie on the
frontend's origin, exactly like every other auth response in this app.
"""

from __future__ import annotations

import logging
import secrets
from urllib.parse import urlencode

import requests
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from . import config, security
from .auth_routes import _set_session_cookie
from .database import get_db
from .models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth/oauth", tags=["oauth"])

_STATE_COOKIE = "oauth_state"

_PROVIDERS = {
    "google": {
        "client_id": config.GOOGLE_CLIENT_ID,
        "client_secret": config.GOOGLE_CLIENT_SECRET,
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
        "scope": "openid email profile",
    },
    "linkedin": {
        "client_id": config.LINKEDIN_CLIENT_ID,
        "client_secret": config.LINKEDIN_CLIENT_SECRET,
        "authorize_url": "https://www.linkedin.com/oauth/v2/authorization",
        "token_url": "https://www.linkedin.com/oauth/v2/accessToken",
        "userinfo_url": "https://api.linkedin.com/v2/userinfo",
        "scope": "openid profile email",
    },
}


def _redirect_uri(provider: str) -> str:
    return f"{config.FRONTEND_URL.rstrip('/')}/api/auth/oauth/{provider}/callback"


def _login_error_redirect(message: str) -> RedirectResponse:
    query = urlencode({"error": message})
    return RedirectResponse(f"{config.FRONTEND_URL.rstrip('/')}/login?{query}", status_code=status.HTTP_302_FOUND)


@router.get("/{provider}/start")
def oauth_start(provider: str) -> RedirectResponse:
    settings = _PROVIDERS.get(provider)
    if settings is None or not settings["client_id"]:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sign-in provider not available.")
    state = secrets.token_urlsafe(24)
    params = {
        "client_id": settings["client_id"],
        "redirect_uri": _redirect_uri(provider),
        "response_type": "code",
        "scope": settings["scope"],
        "state": state,
    }
    redirect = RedirectResponse(f"{settings['authorize_url']}?{urlencode(params)}", status_code=status.HTTP_302_FOUND)
    redirect.set_cookie(
        _STATE_COOKIE, state, max_age=600, httponly=True, samesite="lax", secure=config.COOKIE_SECURE, path="/",
    )
    return redirect


@router.get("/{provider}/callback")
def oauth_callback(
    provider: str,
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    settings = _PROVIDERS.get(provider)
    if settings is None or not settings["client_id"]:
        return _login_error_redirect("Sign-in provider not available.")
    if error or not code:
        return _login_error_redirect("Sign-in was cancelled or failed.")
    if not state or state != request.cookies.get(_STATE_COOKIE):
        return _login_error_redirect("Sign-in session expired. Please try again.")

    try:
        token_resp = requests.post(
            settings["token_url"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": _redirect_uri(provider),
                "client_id": settings["client_id"],
                "client_secret": settings["client_secret"],
            },
            headers={"Accept": "application/json"},
            timeout=15,
        )
        token_resp.raise_for_status()
        access_token = token_resp.json()["access_token"]
        info_resp = requests.get(
            settings["userinfo_url"], headers={"Authorization": f"Bearer {access_token}"}, timeout=15,
        )
        info_resp.raise_for_status()
        info = info_resp.json()
    except (requests.RequestException, KeyError, ValueError):
        logger.exception("OAuth callback failed for provider %s", provider)
        return _login_error_redirect("Sign-in failed. Please try again.")

    subject = str(info.get("sub") or "")
    email = str(info.get("email") or "").strip().lower()
    if not subject or not email:
        return _login_error_redirect("Sign-in provider did not share an email address.")

    column = "google_sub" if provider == "google" else "linkedin_sub"
    user = db.query(User).filter(getattr(User, column) == subject).first()
    if user is None:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            user = User(
                email=email,
                # Random, never-shared value -- password login stays impossible
                # for an OAuth-created account without needing a nullable column.
                hashed_password=security.hash_password(secrets.token_urlsafe(32)),
                full_name=str(info.get("name") or ""),
            )
            db.add(user)
        if info.get("email_verified"):
            user.is_verified = True
        setattr(user, column, subject)
        db.commit()
        db.refresh(user)

    redirect = RedirectResponse(f"{config.FRONTEND_URL.rstrip('/')}/dashboard", status_code=status.HTTP_302_FOUND)
    _set_session_cookie(redirect, user.id)
    return redirect

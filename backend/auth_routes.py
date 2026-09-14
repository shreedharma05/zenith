"""Signup / login / email verification / password reset endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from . import config, security
from .database import get_db
from .deps import get_current_user
from .emailer import send_email
from .models import User
from .schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    ResetPasswordRequest,
    SignupRequest,
    UserOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

_COOKIE_KWARGS = dict(httponly=True, samesite="lax", secure=config.COOKIE_SECURE, path="/")


def _set_session_cookie(response: Response, user_id: int) -> None:
    token = security.create_access_token(user_id)
    response.set_cookie("access_token", token, max_age=config.ACCESS_TOKEN_EXPIRE_MINUTES * 60, **_COOKIE_KWARGS)


def _send_verification_email(user: User) -> None:
    token = security.create_email_token(user.id, "verify_email")
    link = f"{config.FRONTEND_URL}/verify-email?token={token}"
    try:
        send_email(
            user.email,
            "Verify your Zenith account",
            f'<p>Welcome to Zenith.</p><p><a href="{link}">Click here to verify your email</a>. '
            f"This link expires in {config.EMAIL_TOKEN_EXPIRE_MINUTES} minutes.</p>",
        )
    except Exception:
        # The account/token state is already committed -- a delivery failure
        # (bad recipient, SMTP outage, etc.) must not surface as a 500 to the
        # caller. The user can still use "Resend email" once the issue clears.
        logger.exception("Failed to send verification email to %s", user.email)


@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, db: Session = Depends(get_db)) -> User:
    email = payload.email.lower()
    if db.query(User).filter(User.email == email).first() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")
    user = User(email=email, hashed_password=security.hash_password(payload.password), full_name=payload.full_name.strip())
    db.add(user)
    db.commit()
    db.refresh(user)
    _send_verification_email(user)
    return user


@router.post("/login", response_model=UserOut)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> User:
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if user is None or not security.verify_password(payload.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")
    _set_session_cookie(response, user.id)
    return user


@router.post("/logout", response_model=MessageResponse)
def logout(response: Response) -> MessageResponse:
    response.delete_cookie("access_token", path="/")
    return MessageResponse(message="Logged out.")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post("/verify-email", response_model=MessageResponse)
def verify_email(token: str, db: Session = Depends(get_db)) -> MessageResponse:
    user_id = security.decode_token(token, "verify_email")
    user = db.get(User, user_id) if user_id is not None else None
    if user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This verification link is invalid or has expired.")
    user.is_verified = True
    db.commit()
    return MessageResponse(message="Email verified. You can now sign in.")


@router.post("/resend-verification", response_model=MessageResponse)
def resend_verification(user: User = Depends(get_current_user)) -> MessageResponse:
    if user.is_verified:
        return MessageResponse(message="Your email is already verified.")
    _send_verification_email(user)
    return MessageResponse(message="Verification email sent.")


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)) -> MessageResponse:
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if user is not None:
        token = security.create_email_token(user.id, "reset_password")
        link = f"{config.FRONTEND_URL}/reset-password?token={token}"
        try:
            send_email(
                user.email,
                "Reset your Zenith password",
                f'<p><a href="{link}">Click here to reset your password</a>. '
                f"This link expires in {config.EMAIL_TOKEN_EXPIRE_MINUTES} minutes. "
                "If you did not request this, you can safely ignore this email.</p>",
            )
        except Exception:
            logger.exception("Failed to send password reset email to %s", user.email)
    # Same response whether or not the email exists, so we don't leak registered emails.
    return MessageResponse(message="If an account exists for that email, a reset link has been sent.")


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)) -> MessageResponse:
    user_id = security.decode_token(payload.token, "reset_password")
    user = db.get(User, user_id) if user_id is not None else None
    if user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This reset link is invalid or has expired.")
    user.hashed_password = security.hash_password(payload.password)
    db.commit()
    return MessageResponse(message="Password updated. You can now sign in.")

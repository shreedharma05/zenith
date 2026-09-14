"""Transactional email sending, via SMTP. Falls back to logging the email
when SMTP isn't configured, so signup/verify/reset flows stay testable in
local development without a real mail provider."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from . import config

logger = logging.getLogger(__name__)


def send_email(to: str, subject: str, html_body: str) -> None:
    if not config.SMTP_HOST:
        logger.warning("SMTP not configured -- email not sent.\nTo: %s\nSubject: %s\n%s", to, subject, html_body)
        return
    message = EmailMessage()
    message["From"] = config.SMTP_FROM
    message["To"] = to
    message["Subject"] = subject
    message.set_content("This email requires an HTML-capable client.")
    message.add_alternative(html_body, subtype="html")
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
        server.starttls()
        if config.SMTP_USER:
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
        server.send_message(message)

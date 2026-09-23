"""Отправка писем через SMTP (Яндекс / Mail.ru / и т.п.)."""

from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.config import Settings

logger = logging.getLogger(__name__)


def smtp_configured(settings: Settings) -> bool:
    return bool(settings.smtp_host and settings.smtp_user and settings.smtp_password and settings.smtp_from)


def _send_sync(settings: Settings, to_email: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = to_email
    if settings.smtp_reply_to:
        msg["Reply-To"] = settings.smtp_reply_to
    msg.set_content(body)

    if settings.smtp_use_ssl:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=context, timeout=30) as smtp:
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
            smtp.ehlo()
            if settings.smtp_use_starttls:
                context = ssl.create_default_context()
                smtp.starttls(context=context)
                smtp.ehlo()
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)


async def send_access_email(settings: Settings, to_email: str, telegram_url: str) -> bool:
    if not smtp_configured(settings):
        logger.warning("SMTP not configured — skip email to %s", to_email)
        return False
    subject = settings.email_subject
    body = settings.email_body_template.format(telegram_url=telegram_url)
    try:
        await asyncio.to_thread(_send_sync, settings, to_email, subject, body)
        logger.info("Access email sent to %s", to_email)
        return True
    except Exception:
        logger.exception("Failed to send access email to %s", to_email)
        return False

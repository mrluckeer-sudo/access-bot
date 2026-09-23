"""Отправка писем: Resend (HTTPS, работает на Render) или SMTP."""

from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


def smtp_configured(settings: Settings) -> bool:
    return bool(settings.smtp_host and settings.smtp_user and settings.smtp_password and settings.smtp_from)


def resend_configured(settings: Settings) -> bool:
    return bool(settings.resend_api_key and settings.smtp_from)


def email_configured(settings: Settings) -> bool:
    return resend_configured(settings) or smtp_configured(settings)


def _send_smtp_sync(settings: Settings, to_email: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = to_email
    if settings.smtp_reply_to:
        msg["Reply-To"] = settings.smtp_reply_to
    msg.set_content(body)

    if settings.smtp_use_ssl:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=context, timeout=15) as smtp:
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            smtp.ehlo()
            if settings.smtp_use_starttls:
                context = ssl.create_default_context()
                smtp.starttls(context=context)
                smtp.ehlo()
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)


async def _send_resend(settings: Settings, to_email: str, subject: str, body: str) -> None:
    payload = {
        "from": settings.smtp_from,
        "to": [to_email],
        "subject": subject,
        "text": body,
    }
    if settings.smtp_reply_to:
        payload["reply_to"] = settings.smtp_reply_to
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {settings.resend_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Resend HTTP {resp.status_code}: {resp.text[:300]}")


async def send_access_email(settings: Settings, to_email: str, telegram_url: str) -> bool:
    if not email_configured(settings):
        logger.warning("Email not configured — skip send to %s", to_email)
        return False

    subject = settings.email_subject
    body = settings.email_body_template.format(telegram_url=telegram_url)
    try:
        if resend_configured(settings):
            await _send_resend(settings, to_email, subject, body)
        else:
            # На Render Free порты 465/587 часто закрыты → Network is unreachable
            await asyncio.to_thread(_send_smtp_sync, settings, to_email, subject, body)
        logger.info("Access email sent to %s", to_email)
        return True
    except Exception:
        logger.exception("Failed to send access email to %s", to_email)
        return False

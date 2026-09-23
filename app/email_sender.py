"""Отправка писем: Brevo / Unisender / Resend (HTTPS) или SMTP."""

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


def brevo_configured(settings: Settings) -> bool:
    return bool(settings.brevo_api_key and settings.smtp_from)


def unisender_go_configured(settings: Settings) -> bool:
    return bool(settings.unisender_go_api_key and settings.smtp_from)


def unisender_classic_configured(settings: Settings) -> bool:
    return bool(settings.unisender_api_key and settings.smtp_from and settings.unisender_list_id)


def email_configured(settings: Settings) -> bool:
    return (
        brevo_configured(settings)
        or unisender_go_configured(settings)
        or unisender_classic_configured(settings)
        or resend_configured(settings)
        or smtp_configured(settings)
    )


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


async def _send_brevo(settings: Settings, to_email: str, subject: str, body: str) -> None:
    payload: dict = {
        "sender": {
            "email": settings.smtp_from,
            "name": settings.smtp_from_name or "Volgina",
        },
        "to": [{"email": to_email}],
        "subject": subject,
        "textContent": body,
        "htmlContent": body.replace("\n", "<br>\n"),
    }
    if settings.smtp_reply_to:
        payload["replyTo"] = {"email": settings.smtp_reply_to}

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={
                "api-key": settings.brevo_api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json=payload,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Brevo HTTP {resp.status_code}: {resp.text[:400]}")


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


async def _send_unisender_go(settings: Settings, to_email: str, subject: str, body: str) -> None:
    base = settings.unisender_go_base_url.rstrip("/")
    url = f"{base}/email/send.json"
    message: dict = {
        "recipients": [{"email": to_email}],
        "from_email": settings.smtp_from,
        "subject": subject,
        "body": {"plaintext": body, "html": body.replace("\n", "<br>\n")},
        "track_links": 0,
        "track_read": 0,
        "skip_unsubscribe": 1,
    }
    if settings.smtp_from_name:
        message["from_name"] = settings.smtp_from_name
    if settings.smtp_reply_to:
        message["reply_to"] = settings.smtp_reply_to

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            url,
            headers={
                "X-API-KEY": settings.unisender_go_api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json={"message": message},
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Unisender Go HTTP {resp.status_code}: {resp.text[:400]}")
        data = resp.json()
        if isinstance(data, dict) and data.get("status") == "error":
            raise RuntimeError(f"Unisender Go error: {data}")


async def _send_unisender_classic(settings: Settings, to_email: str, subject: str, body: str) -> None:
    """Классический Unisender.com sendEmail (нужен list_id)."""
    payload = {
        "format": "json",
        "api_key": settings.unisender_api_key,
        "email": to_email,
        "sender_name": settings.smtp_from_name or "Volgina",
        "sender_email": settings.smtp_from,
        "subject": subject,
        "body": body.replace("\n", "<br>\n"),
        "list_id": settings.unisender_list_id,
        "error_checking": 1,
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            "https://api.unisender.com/ru/api/sendEmail",
            data=payload,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Unisender HTTP {resp.status_code}: {resp.text[:400]}")
        data = resp.json()
        if isinstance(data, dict) and data.get("error"):
            raise RuntimeError(f"Unisender error: {data}")


async def send_access_email(settings: Settings, to_email: str, telegram_url: str) -> bool:
    if not email_configured(settings):
        logger.warning("Email not configured — skip send to %s", to_email)
        return False

    subject = settings.email_subject
    body = settings.email_body_template.format(telegram_url=telegram_url)
    try:
        if brevo_configured(settings):
            await _send_brevo(settings, to_email, subject, body)
        elif unisender_go_configured(settings):
            await _send_unisender_go(settings, to_email, subject, body)
        elif unisender_classic_configured(settings):
            await _send_unisender_classic(settings, to_email, subject, body)
        elif resend_configured(settings):
            await _send_resend(settings, to_email, subject, body)
        else:
            await asyncio.to_thread(_send_smtp_sync, settings, to_email, subject, body)
        logger.info("Access email sent to %s", to_email)
        return True
    except Exception:
        logger.exception("Failed to send access email to %s", to_email)
        return False

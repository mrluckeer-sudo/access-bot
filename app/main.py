from __future__ import annotations

import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Update
from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.bot_handlers import setup_bot_handlers
from app.config import get_settings
from app.db import Database
from app.email_sender import send_access_email, smtp_configured
from app.robokassa import (
    payment_signature,
    verify_result_signature,
    verify_success_signature,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()
db = Database(settings.database_path)
bot = Bot(
    token=settings.bot_token,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await db.connect()
    setup_bot_handlers(dp, db, settings)
    await bot.set_webhook(
        url=settings.webhook_url,
        drop_pending_updates=True,
        allowed_updates=["message"],
    )
    logger.info("Webhook set: %s", settings.webhook_url)
    yield
    await bot.session.close()
    await db.close()


app = FastAPI(title="Access Bot", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")


def _collect_params(data: dict[str, Any]) -> dict[str, str]:
    return {str(k): str(v) for k, v in data.items() if v is not None}


def _extract_email(data: dict[str, str]) -> str | None:
    for key in ("EMail", "Email", "email", "Shp_email", "Shp_Email", "shp_email"):
        value = (data.get(key) or "").strip()
        if value and _EMAIL_RE.match(value):
            return value
    return None


async def _robokassa_payload(request: Request) -> dict[str, str]:
    if request.method == "POST":
        form = await request.form()
        return _collect_params(dict(form))
    return _collect_params(dict(request.query_params))


async def _resolve_chat_email(inv_id: int, data: dict[str, str]) -> str | None:
    """Email: уже сохранённый → Robokassa → свежая форма Tilda."""
    existing = await db.get_by_inv_id(inv_id)
    if existing and existing["email"]:
        return existing["email"]

    email = _extract_email(data)
    if email:
        return email

    lead = await db.claim_pending_lead(
        product=settings.default_product,
        inv_id=inv_id,
        max_age_minutes=settings.lead_match_minutes,
    )
    if lead:
        logger.info(
            "Matched Tilda lead id=%s email=%s → InvId=%s",
            lead["id"],
            lead["email"],
            inv_id,
        )
        return lead["email"]
    return None


def _extract_email_from_tilda(data: dict[str, str]) -> str | None:
    # Tilda: Email / email / E-mail / переменная поля
    for key, value in data.items():
        key_l = key.lower().replace("-", "").replace("_", "")
        if key_l in {"email", "e-mail", "mail", "почта"} or "email" in key.lower():
            value = (value or "").strip()
            if value and _EMAIL_RE.match(value):
                return value
    return _extract_email(data)


def _extract_name_from_tilda(data: dict[str, str]) -> str | None:
    for key in ("Name", "name", "Имя", "FIO", "fio"):
        value = (data.get(key) or "").strip()
        if value:
            return value
    return None


def _extract_product_from_tilda(data: dict[str, str]) -> str:
    for key in ("product", "Product", "Shp_product", "товар"):
        value = (data.get(key) or "").strip().lower()
        if value:
            return value
    return settings.default_product


async def _ensure_chat_access(inv_id: int, out_sum: str, email: str | None) -> tuple[str, str, bool]:
    """
    Создаёт/обновляет оплату чата, шлёт письмо один раз.
    Returns: token, telegram_url, email_already_sent_or_just_sent
    """
    token_probe = await db.upsert_paid(inv_id, out_sum, email=email)
    telegram_url = f"https://t.me/{settings.bot_username}?start={token_probe}"
    token = await db.upsert_paid(inv_id, out_sum, email=email, telegram_url=telegram_url)

    payment = await db.get_by_inv_id(inv_id)
    already_sent = bool(payment and payment["email_sent_at"])
    mail = email or (payment["email"] if payment else None)

    if mail and not already_sent:
        sent = await send_access_email(settings, mail, telegram_url)
        if sent:
            await db.mark_email_sent(inv_id)
            already_sent = True

    return token, telegram_url, already_sent


async def _forward_result_to_tilda(data: dict[str, str]) -> None:
    """Чтобы курсы на Tilda продолжали отмечаться оплаченными."""
    url = settings.tilda_result_url
    if not url:
        return
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, data=data)
            logger.info("Forwarded Result to Tilda status=%s body=%s", resp.status_code, resp.text[:120])
    except Exception:
        logger.exception("Failed to forward ResultURL to Tilda")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.api_route("/tilda/webhook", methods=["POST", "OPTIONS"])
async def tilda_form_webhook(request: Request) -> PlainTextResponse:
    """
    Webhook формы Tilda. Обязательно ответить ровно `ok` за < 7 сек.
    Настройки: Сайт → Формы → Webhook → этот URL.
    """
    if request.method == "OPTIONS":
        return PlainTextResponse(
            "ok",
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            },
        )

    try:
        form = await request.form()
        data = _collect_params(dict(form))
    except Exception:
        try:
            data = _collect_params(await request.json())
        except Exception:
            data = {}

    email = _extract_email_from_tilda(data)
    if not email:
        logger.warning("Tilda webhook without email keys=%s", list(data.keys()))
        # Всё равно ok — иначе Tilda покажет ошибку формы
        return PlainTextResponse(
            "ok",
            headers={"Access-Control-Allow-Origin": "*"},
        )

    product = _extract_product_from_tilda(data)
    lead_id = await db.create_pending_lead(
        email=email,
        product=product,
        name=_extract_name_from_tilda(data),
        formid=data.get("formid") or data.get("formname"),
        tranid=data.get("tranid"),
    )
    logger.info("Tilda lead saved id=%s email=%s product=%s", lead_id, email, product)
    return PlainTextResponse(
        "ok",
        headers={"Access-Control-Allow-Origin": "*"},
    )


@app.post(settings.webhook_path)
async def telegram_webhook(request: Request) -> dict[str, bool]:
    payload = await request.json()
    update = Update.model_validate(payload, context={"bot": bot})
    await dp.feed_update(bot, update)
    return {"ok": True}


@app.api_route("/robokassa/result", methods=["GET", "POST"])
async def robokassa_result(request: Request) -> PlainTextResponse:
    """
    ResultURL (поставьте его в Robokassa вместо Tilda).
    — для чата: токен + письмо (даже если человек не нажал «вернуться в магазин»);
    — всем: проксируем уведомление на Tilda, чтобы курсы не сломались.
    """
    data = await _robokassa_payload(request)

    out_sum = data.get("OutSum", "")
    inv_id = data.get("InvId", "")
    signature = data.get("SignatureValue", "")

    if not out_sum or not inv_id or not signature:
        return PlainTextResponse("bad request", status_code=400)

    if not verify_result_signature(
        out_sum, inv_id, signature, settings.robokassa_password2, data
    ):
        logger.warning("Invalid ResultURL signature for InvId=%s", inv_id)
        return PlainTextResponse("bad sign", status_code=400)

    email = await _resolve_chat_email(int(inv_id), data)

    if settings.is_chat_access_payment(out_sum):
        token, telegram_url, mailed = await _ensure_chat_access(int(inv_id), out_sum, email)
        logger.info(
            "Chat payment Result InvId=%s token=%s… email=%s mailed=%s",
            inv_id,
            token[:8],
            email,
            mailed,
        )
    else:
        logger.info("Course/other payment Result InvId=%s sum=%s", inv_id, out_sum)

    await _forward_result_to_tilda(data)
    return PlainTextResponse(f"OK{inv_id}")


async def _handle_payment_success(request: Request):
    data = await _robokassa_payload(request)

    out_sum = data.get("OutSum", "")
    inv_id = data.get("InvId", "")
    signature = data.get("SignatureValue", "")

    if not out_sum or not inv_id or not signature:
        return templates.TemplateResponse(
            request,
            "success.html",
            {
                "ok": False,
                "error": "Нет данных об оплате.",
                "telegram_url": None,
                "email_note": None,
                "auto_open_seconds": 0,
            },
        )

    if not verify_success_signature(
        out_sum, inv_id, signature, settings.robokassa_password1, data
    ):
        return templates.TemplateResponse(
            request,
            "success.html",
            {
                "ok": False,
                "error": "Подпись платежа не совпала.",
                "telegram_url": None,
                "email_note": None,
                "auto_open_seconds": 0,
            },
        )

    if not settings.is_chat_access_payment(out_sum):
        logger.info("Non-chat payment InvId=%s sum=%s → course success page", inv_id, out_sum)
        return RedirectResponse(settings.course_success_url, status_code=303)

    email = await _resolve_chat_email(int(inv_id), data)
    _token, telegram_url, mailed = await _ensure_chat_access(int(inv_id), out_sum, email)

    if mailed and email:
        email_note = f"Дублируем ссылку на почту {email} — если закроете страницу, письмо останется."
    elif email and not smtp_configured(settings):
        email_note = "Почта получена, но SMTP ещё не настроен — письмо не отправлено."
    elif email:
        email_note = "Не удалось отправить письмо — используйте кнопку ниже или форму восстановления."
    else:
        email_note = (
            "Не нашли email с формы. Сохраните ссылку ниже или напишите в поддержку. "
            "Проверьте, что webhook формы Tilda включён."
        )

    return templates.TemplateResponse(
        request,
        "success.html",
        {
            "ok": True,
            "error": "",
            "telegram_url": telegram_url,
            "email_note": email_note,
            "auto_open_seconds": settings.auto_open_telegram_seconds,
        },
    )


@app.api_route("/", methods=["GET", "POST", "HEAD"])
async def root(request: Request):
    if request.method == "HEAD":
        return PlainTextResponse("", status_code=200)
    data = await _robokassa_payload(request)
    if data.get("OutSum") and data.get("InvId") and data.get("SignatureValue"):
        return await _handle_payment_success(request)
    return PlainTextResponse(
        "Access bot OK. Success URL: "
        f"{settings.public_base_url.rstrip('/')}/success"
    )


@app.api_route("/success", methods=["GET", "POST", "HEAD"])
async def payment_success(request: Request):
    if request.method == "HEAD":
        return PlainTextResponse("", status_code=200)
    return await _handle_payment_success(request)


@app.api_route("/fail", methods=["GET", "POST", "HEAD"], response_model=None)
async def payment_fail(request: Request):
    if request.method == "HEAD":
        return PlainTextResponse("", status_code=200)
    return RedirectResponse(settings.course_fail_url, status_code=303)


@app.api_route("/recover", methods=["GET", "POST"], response_model=None)
async def recover_access(request: Request, email: str | None = Form(None)):
    """Повторно показать ссылку по email с формы (если токен ещё не использован)."""
    if request.method == "GET":
        return templates.TemplateResponse(
            request,
            "recover.html",
            {"ok": None, "telegram_url": None, "message": None},
        )

    mail = (email or "").strip()
    if not mail or not _EMAIL_RE.match(mail):
        return templates.TemplateResponse(
            request,
            "recover.html",
            {"ok": False, "telegram_url": None, "message": "Введите корректный email."},
        )

    payment = await db.get_latest_unused_by_email(mail)
    if not payment:
        return templates.TemplateResponse(
            request,
            "recover.html",
            {
                "ok": False,
                "telegram_url": None,
                "message": "Активная ссылка для этого email не найдена. Напишите в поддержку.",
            },
        )

    telegram_url = payment["telegram_url"] or (
        f"https://t.me/{settings.bot_username}?start={payment['access_token']}"
    )
    return templates.TemplateResponse(
        request,
        "recover.html",
        {
            "ok": True,
            "telegram_url": telegram_url,
            "message": "Нашли вашу ссылку. Перейдите в Telegram:",
        },
    )


@app.get("/dev/fake-paid")
async def fake_paid(
    inv_id: int = Query(..., ge=1),
    email: str | None = Query(None),
) -> RedirectResponse:
    if settings.robokassa_is_test != 1:
        raise HTTPException(403, "Disabled outside test mode")
    mail = email if email and _EMAIL_RE.match(email) else None
    _token, url, _mailed = await _ensure_chat_access(inv_id, settings.access_price, mail)
    return RedirectResponse(url)


@app.get("/dev/pay-link")
async def pay_link(inv_id: int = Query(..., ge=1)) -> dict[str, str]:
    if settings.robokassa_is_test != 1:
        raise HTTPException(403, "Disabled outside test mode")
    out_sum = settings.access_price
    sign = payment_signature(
        settings.robokassa_merchant_login,
        out_sum,
        inv_id,
        settings.robokassa_password1,
    )
    base = "https://auth.robokassa.ru/Merchant/Index.aspx"
    url = (
        f"{base}?MerchantLogin={settings.robokassa_merchant_login}"
        f"&OutSum={out_sum}&InvId={inv_id}"
        f"&Description=Access+to+private+chat"
        f"&SignatureValue={sign}&IsTest=1"
    )
    return {"payment_url": url, "inv_id": str(inv_id)}

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Update
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.bot_handlers import setup_bot_handlers
from app.config import get_settings
from app.db import Database
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
    # Не вызываем delete_webhook: при редеплое старый инстанс
    # иначе снимает вебхук у нового.
    await bot.session.close()
    await db.close()


app = FastAPI(title="Access Bot", lifespan=lifespan)


def _collect_params(data: dict[str, Any]) -> dict[str, str]:
    return {str(k): str(v) for k, v in data.items() if v is not None}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(settings.webhook_path)
async def telegram_webhook(request: Request) -> dict[str, bool]:
    payload = await request.json()
    update = Update.model_validate(payload, context={"bot": bot})
    await dp.feed_update(bot, update)
    return {"ok": True}


@app.api_route("/robokassa/result", methods=["GET", "POST"])
async def robokassa_result(request: Request) -> PlainTextResponse:
    """ResultURL: серверное уведомление от Robokassa. Ответ должен быть OK{InvId}."""
    if request.method == "POST":
        form = await request.form()
        data = _collect_params(dict(form))
    else:
        data = _collect_params(dict(request.query_params))

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

    token = await db.upsert_paid(int(inv_id), out_sum)
    logger.info("Payment confirmed InvId=%s token=%s…", inv_id, token[:8])
    return PlainTextResponse(f"OK{inv_id}")


@app.api_route("/success", methods=["GET", "POST"])
async def payment_success(request: Request) -> HTMLResponse:
    """SuccessURL: пользователь после оплаты. Показываем кнопку в Telegram."""
    if request.method == "POST":
        form = await request.form()
        data = _collect_params(dict(form))
    else:
        data = _collect_params(dict(request.query_params))

    out_sum = data.get("OutSum", "")
    inv_id = data.get("InvId", "")
    signature = data.get("SignatureValue", "")

    error = "Неизвестная ошибка"
    telegram_url = None
    ok = False

    if not out_sum or not inv_id or not signature:
        error = "Нет данных об оплате."
    elif not verify_success_signature(
        out_sum, inv_id, signature, settings.robokassa_password1, data
    ):
        error = "Подпись платежа не совпала."
    else:
        payment = await db.get_by_inv_id(int(inv_id))
        if payment:
            token = payment["access_token"]
        else:
            # SuccessURL иногда приходит раньше ResultURL — создаём токен
            # по проверенной подписи Success, ResultURL потом просто подтвердит.
            token = await db.upsert_paid(int(inv_id), out_sum)

        telegram_url = f"https://t.me/{settings.bot_username}?start={token}"
        ok = True

    return templates.TemplateResponse(
        request,
        "success.html",
        {
            "ok": ok,
            "error": error,
            "telegram_url": telegram_url,
        },
    )


@app.get("/fail")
async def payment_fail() -> HTMLResponse:
    return HTMLResponse(
        "<html><body style='font-family:sans-serif;text-align:center;padding:48px'>"
        "<h1>Оплата не завершена</h1>"
        "<p>Попробуйте ещё раз на сайте.</p>"
        "</body></html>"
    )


@app.get("/dev/fake-paid")
async def fake_paid(inv_id: int = Query(..., ge=1)) -> RedirectResponse:
    """Тест без Robokassa (только при ROBOKASSA_IS_TEST=1)."""
    if settings.robokassa_is_test != 1:
        raise HTTPException(403, "Disabled outside test mode")
    token = await db.upsert_paid(inv_id, settings.access_price)
    url = f"https://t.me/{settings.bot_username}?start={token}"
    return RedirectResponse(url)


@app.get("/dev/pay-link")
async def pay_link(inv_id: int = Query(..., ge=1)) -> dict[str, str]:
    """Тестовая ссылка на оплату Robokassa."""
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

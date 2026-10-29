"""Создание Bot с опциональным прокси Cloudflare Worker."""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode

from app.config import Settings

logger = logging.getLogger(__name__)


def create_bot(settings: Settings) -> Bot:
    session_kwargs: dict = {}
    base = (settings.telegram_api_base or "").rstrip("/")
    if base:
        api = TelegramAPIServer.from_base(base, is_local=False)
        session_kwargs["api"] = api
        logger.info("Telegram API via proxy: %s", base)
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=AiohttpSession(**session_kwargs),
    )

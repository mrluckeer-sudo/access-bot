"""
Как узнать ID канала/чата:

1. Впишите BOT_TOKEN в файл .env (в корне проекта).
2. В Терминале Cursor:

   cd "/Users/leonov/Downloads/Чатбот"
   source .venv/bin/activate
   python scripts/get_chat_id.py

3. Опубликуйте любой пост в канале (или напишите в группе).
4. В терминале появится строка TELEGRAM_CHAT_ID=...
5. Скопируйте число в .env → TELEGRAM_CHAT_ID=...
6. Остановите скрипт: Ctrl+C

Альтернатива без скрипта: перешлите пост канала боту @userinfobot — он покажет Chat ID.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

TOKEN = os.environ.get("BOT_TOKEN", "").strip()
if not TOKEN or TOKEN.startswith("123456"):
    raise SystemExit(
        "Сначала откройте файл .env в корне проекта и вставьте реальный BOT_TOKEN от BotFather."
    )


def _print_id(chat_id: int, title: str | None = None) -> None:
    line = f"TELEGRAM_CHAT_ID={chat_id}"
    if title:
        line += f"  # {title}"
    print(line)
    print("Скопируйте число в .env и нажмите Ctrl+C, чтобы остановить скрипт.")


async def main() -> None:
    # На Python 3.9 Dispatcher нужно создавать внутри event loop
    dp = Dispatcher()

    @dp.channel_post()
    async def on_channel_post(message: Message) -> None:
        _print_id(message.chat.id, message.chat.title)

    @dp.message(F.chat.type.in_({"group", "supergroup"}))
    async def on_group_message(message: Message) -> None:
        _print_id(message.chat.id, message.chat.title)
        try:
            await message.answer(f"TELEGRAM_CHAT_ID={message.chat.id}")
        except Exception:
            pass

    @dp.message(F.forward_from_chat)
    async def on_forward(message: Message) -> None:
        chat = message.forward_from_chat
        if chat:
            _print_id(chat.id, getattr(chat, "title", None))
            await message.answer(f"TELEGRAM_CHAT_ID={chat.id}")

    bot = Bot(TOKEN)
    me = await bot.get_me()
    print(f"Бот @{me.username} запущен.")
    print("Опубликуйте пост в канале (бот — админ) или напишите в группе.")
    print("Либо перешлите пост канала этому боту в личку.")
    await dp.start_polling(bot, allowed_updates=["message", "channel_post"])


if __name__ == "__main__":
    asyncio.run(main())

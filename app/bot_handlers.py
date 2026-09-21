from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import Message

from app.config import Settings
from app.db import Database

router = Router()


def setup_bot_handlers(dp: Dispatcher, db: Database, settings: Settings) -> None:
    @router.message(CommandStart())
    async def on_start(message: Message, command: CommandObject, bot: Bot) -> None:
        token = (command.args or "").strip()
        if not token:
            await message.answer(
                "Чтобы получить доступ, перейдите по кнопке «Перейти в Telegram» "
                "со страницы после оплаты."
            )
            return

        payment = await db.get_by_token(token)
        if not payment or payment["status"] != "paid":
            await message.answer(settings.welcome_invalid_text)
            return

        if payment["used_at"]:
            if payment["telegram_user_id"] == message.from_user.id and payment["invite_link"]:
                await message.answer(
                    f"{settings.welcome_paid_text}\n\n{payment['invite_link']}"
                )
            else:
                await message.answer(settings.welcome_invalid_text)
            return

        expire_at = datetime.now(timezone.utc) + timedelta(seconds=settings.invite_expire_seconds)
        invite = await bot.create_chat_invite_link(
            chat_id=settings.telegram_chat_id,
            name=f"order-{payment['inv_id']}"[:32],
            member_limit=1,
            expire_date=expire_at,
        )

        marked = await db.mark_used(token, message.from_user.id, invite.invite_link)
        if not marked:
            await message.answer(settings.welcome_invalid_text)
            return

        await message.answer(f"{settings.welcome_paid_text}\n\n{invite.invite_link}")

    @router.message(F.text)
    async def on_text(message: Message) -> None:
        await message.answer(
            "Я выдаю доступ после оплаты на сайте. "
            "Если оплата уже прошла — откройте бота по кнопке со страницы «Спасибо»."
        )

    dp.include_router(router)

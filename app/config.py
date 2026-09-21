from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str
    bot_username: str
    telegram_chat_id: int
    public_base_url: str
    webhook_secret: str = "change_me"

    robokassa_merchant_login: str
    robokassa_password1: str
    robokassa_password2: str
    robokassa_is_test: int = 1

    access_price: str = "990.00"
    database_path: str = "./data/bot.db"

    welcome_paid_text: str = (
        "Оплата подтверждена. Вот ваша одноразовая ссылка в закрытый чат "
        "(действует ограниченное время):"
    )
    welcome_invalid_text: str = (
        "Ссылка недействительна или уже использована. "
        "Если вы оплатили доступ — напишите в поддержку."
    )
    invite_expire_seconds: int = 3600

    @property
    def webhook_path(self) -> str:
        return f"/telegram/webhook/{self.webhook_secret}"

    @property
    def webhook_url(self) -> str:
        return f"{self.public_base_url.rstrip('/')}{self.webhook_path}"


@lru_cache
def get_settings() -> Settings:
    return Settings()

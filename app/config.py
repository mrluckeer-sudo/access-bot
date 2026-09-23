from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_amount(value: str) -> str:
    """990 / 990.0 / 990,00 → 990.00"""
    cleaned = value.strip().replace(",", ".")
    try:
        return f"{float(cleaned):.2f}"
    except ValueError:
        return cleaned


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
    course_success_url: str = "https://logopedvolgina.ru/success"
    course_fail_url: str = "https://logopedvolgina.ru/fail"
    tilda_result_url: str = "https://forms.tildacdn.com/payment/robokassa/"

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

    # Склейка формы Tilda с оплатой
    lead_match_minutes: int = 60
    default_product: str = "chat"
    tilda_webhook_path: str = "/tilda/webhook"

    # SMTP (например Яндекс: smtp.yandex.ru, порт 465, SSL)
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_from_name: str = "Volgina"
    smtp_reply_to: str = ""
    smtp_use_ssl: int = 1
    smtp_use_starttls: int = 0

    # Brevo (HTTPS) — рекомендуется: без DNS, подтверждение sender кодом
    brevo_api_key: str = ""

    # Unisender Go (нужен домен ссылок NS/CNAME — на Tilda DNS обычно нельзя)
    unisender_go_api_key: str = ""
    unisender_go_base_url: str = "https://goapi.unisender.ru/ru/transactional/api/v1"

    # Классический Unisender.com (нужен list_id)
    unisender_api_key: str = ""
    unisender_list_id: str = ""

    # Resend.com API (HTTPS) — нужен CNAME в DNS (на Tilda DNS нельзя)
    resend_api_key: str = ""

    email_subject: str = "Ваша ссылка в Telegram-чат — Volgina"
    email_body_template: str = (
        "Здравствуйте!\n\n"
        "Оплата прошла успешно. Чтобы получить доступ в закрытый чат, "
        "перейдите по ссылке и нажмите Start у бота:\n\n"
        "{telegram_url}\n\n"
        "Если кнопка «Вернуться в магазин» на Robokassa вас смутила — "
        "этого письма достаточно, оплата уже учтена.\n\n"
        "С уважением,\nVolgina"
    )
    # Через сколько секунд автоматически открыть Telegram на success-странице (0 = выкл)
    auto_open_telegram_seconds: int = 4

    @property
    def access_prices(self) -> set[str]:
        raw = self.access_price.replace(";", ",")
        return {normalize_amount(p) for p in raw.split(",") if p.strip()}

    def is_chat_access_payment(self, out_sum: str) -> bool:
        return normalize_amount(out_sum) in self.access_prices

    @property
    def webhook_path(self) -> str:
        return f"/telegram/webhook/{self.webhook_secret}"

    @property
    def webhook_url(self) -> str:
        return f"{self.public_base_url.rstrip('/')}{self.webhook_path}"


@lru_cache
def get_settings() -> Settings:
    return Settings()

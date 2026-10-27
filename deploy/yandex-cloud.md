# Деплой на Yandex Cloud

Рекомендуемый вариант для SQLite: **Compute Cloud VM + Docker** (диск постоянный, HTTPS через Caddy).

## 1. ВМ

1. Консоль → Compute Cloud → создать ВМ (Ubuntu 22.04, 2 vCPU / 2 GB, публичный IP).
2. Открыть порты **80** и **443** в группе безопасности.
3. SSH на машину.

```bash
sudo apt update && sudo apt install -y docker.io docker-compose-v2
sudo usermod -aG docker $USER
# перелогиньтесь
```

## 2. Приложение

```bash
mkdir -p ~/access-bot/data && cd ~/access-bot
# скопируйте Dockerfile, requirements.txt, app/ (или git clone)
nano .env   # заполните как в .env.example
```

`docker-compose.yml`:

```yaml
services:
  app:
    build: .
    restart: unless-stopped
    env_file: .env
    environment:
      DATABASE_PATH: /data/bot.db
      PORT: "8080"
    volumes:
      - ./data:/data
    ports:
      - "8080:8080"

  caddy:
    image: caddy:2
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
      - caddy_config:/config

volumes:
  caddy_data:
  caddy_config:
```

`Caddyfile` (подставьте свой домен, A-запись → IP ВМ):

```
bot.example.ru {
  reverse_proxy app:8080
}
```

```bash
docker compose up -d --build
curl https://bot.example.ru/health
```

## 3. Переменные

В `.env` обязательно:

- `PUBLIC_BASE_URL=https://bot.example.ru`
- `CLOUDPAYMENTS_API_SECRET=...`
- `BREVO_API_KEY=...`, `SMTP_FROM=...`
- Telegram-токены как раньше

## 4. CloudPayments

В ЛК CloudPayments → сайт → уведомления:

| Тип | URL |
|-----|-----|
| Check | `https://bot.example.ru/cloudpayments/check` |
| Pay | `https://bot.example.ru/cloudpayments/pay` |

Формат: **CloudPayments** (form POST). HTTP-метод POST.

На Tilda в настройках CloudPayments Public ID / API password как обычно.

## 5. Telegram webhook

После старта сервис сам вызывает `setWebhook` на `{PUBLIC_BASE_URL}/telegram/webhook/{WEBHOOK_SECRET}`.

## Альтернатива: Serverless Containers

Можно, но для SQLite неудобно (эфемерный диск). Тогда нужна внешняя БД (Managed PostgreSQL) — отдельный рефакторинг.

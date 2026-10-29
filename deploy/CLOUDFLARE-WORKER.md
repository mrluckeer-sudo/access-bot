# Cloudflare Worker — прокси Telegram API (бесплатно)

Нужен один раз, чтобы ВМ в Yandex могла вызывать Bot API.

## В Dashboard (без CLI)

1. Откройте [dash.cloudflare.com](https://dash.cloudflare.com) → слева **Workers & Pages**.
2. **Create** → **Create Worker**.
3. Имя, например: `telegram-api-proxy` → **Deploy**.
4. **Edit code** → удалите весь шаблон → вставьте содержимое файла `deploy/telegram-api-proxy/worker.js` из репозитория.
5. **Deploy**.
6. Скопируйте URL вида:
   `https://telegram-api-proxy.<ваш-сабдомен>.workers.dev`  
   (кнопка Visit / в Overview).

7. Напишите этот URL мне **или** сами на ВМ:

```bash
# на ВМ
nano ~/access-bot/.env
# добавьте строку (без слэша в конце):
TELEGRAM_API_BASE=https://telegram-api-proxy.XXXX.workers.dev

sudo systemctl restart access-bot
```

Проверка с ВМ:
```bash
curl -sS "$TELEGRAM_API_BASE/health"
# и (подставьте токен бота):
curl -sS "$TELEGRAM_API_BASE/bot<BOT_TOKEN>/getMe"
```

## Через CLI (если удобнее)

```bash
cd deploy/telegram-api-proxy
npx wrangler login
npx wrangler deploy
```

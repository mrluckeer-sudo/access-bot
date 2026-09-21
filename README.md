# Чат-бот доступа после оплаты (Tilda + Robokassa + Telegram)

Бот выдаёт **одноразовую ссылку** в закрытый Telegram-чат после успешной оплаты на сайте.

```
Оплата на Tilda (Robokassa)
        ↓
ResultURL → ваш сервер (фиксирует оплату, создаёт токен)
SuccessURL → страница «Спасибо» с кнопкой t.me/Бот?start=ТОКЕН
        ↓
Пользователь открывает бота → бот отдаёт invite-ссылку (1 человек)
```

Позже тот же сервер можно расширить адаптером для **Max** — логика оплаты и токенов останется общей.

---

## Что нужно заранее

1. Бот в Telegram через [@BotFather](https://t.me/BotFather) → `/newbot` → сохранить **токен** и **username** (без `@`).
2. Закрытый супергруппа/канал: добавить бота **администратором** с правом **приглашать пользователей** (Invite users via link).
3. Магазин в [Robokassa](https://www.robokassa.ru/) (логин, Пароль #1, Пароль #2).
4. Сайт на Tilda с привязанной Robokassa.

---

## Быстрый старт локально

```bash
cd "Чатбот"
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# заполните .env
```

### Узнать ID чата

1. Временно в `.env` укажите любые заглушки (или только `BOT_TOKEN`).
2. Остановите основной сервер (если запущен).
3. Запустите:

```bash
python scripts/get_chat_id.py
```

4. Напишите любое сообщение в закрытом чате (бот должен быть участником) — в ответ придёт `TELEGRAM_CHAT_ID=...`.
5. Вставьте это значение в `.env`.

### Запуск сервера

Нужен **публичный HTTPS URL** (Telegram и Robokassa не ходят на `localhost`).  
Для локальной отладки удобен [ngrok](https://ngrok.com/):

```bash
ngrok http 8000
# скопируйте https://xxxx.ngrok-free.app в PUBLIC_BASE_URL в .env
```

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Проверка: откройте `https://ваш-url/health` → `{"status":"ok"}`.

### Тест без оплаты

При `ROBOKASSA_IS_TEST=1`:

```
https://ваш-url/dev/fake-paid?inv_id=1001
```

Откроется бот с валидным токеном. Должна прийти одноразовая ссылка в чат.

---

## Настройка Robokassa

В личном кабинете Robokassa → технические настройки магазина:

| Поле | Значение |
|------|----------|
| Result URL | `https://ВАШ_ДОМЕН/robokassa/result` |
| Success URL | `https://ВАШ_ДОМЕН/success` |
| Fail URL | `https://ВАШ_ДОМЕН/fail` |
| Метод | POST (или GET — сервер принимает оба) |
| Алгоритм | MD5 |

Пароли #1 и #2 из кабинета → в `.env` (`ROBOKASSA_PASSWORD1` / `ROBOKASSA_PASSWORD2`).

На Tilda оставьте оплату через Robokassa как обычно: после оплаты Robokassa сама вызовет Result/Success URL.  
Страницу «Спасибо» на Tilda можно не использовать — пользователь попадёт на нашу `/success` с кнопкой «Перейти в Telegram».

---

## Переменные окружения (`.env`)

См. `.env.example`. Обязательные:

- `BOT_TOKEN`, `BOT_USERNAME`, `TELEGRAM_CHAT_ID`
- `PUBLIC_BASE_URL` — публичный HTTPS без `/` в конце
- `WEBHOOK_SECRET` — любая длинная случайная строка
- `ROBOKASSA_MERCHANT_LOGIN`, `ROBOKASSA_PASSWORD1`, `ROBOKASSA_PASSWORD2`

Перед боем поставьте `ROBOKASSA_IS_TEST=0` (отключает `/dev/*`).

---

## Где хостить (бесплатно / дёшево)

| Вариант | Плюсы | Минусы |
|---------|--------|--------|
| **[Render](https://render.com)** Free Web Service | Просто: Docker/Python, HTTPS из коробки | Засыпает без трафика (~15 мин), диск временный |
| **[Amvera](https://amvera.ru)** | РФ, русский интерфейс, бесплатный тариф | Лимиты по ресурсам |
| **[Fly.io](https://fly.io)** | Удобный Docker, есть free allowance | Нужна карта для аккаунта |
| **Yandex Cloud** (у вас уже есть) | Стабильно, в РФ, можно Serverless Containers / VM | Не «совсем бесплатно», но грант/пейдж-аз-ю-гоу |

**Рекомендация для старта:** Render или Amvera — быстрее всего поднять каркас.  
Когда появятся оплаты — перенести на **Yandex Cloud** (постоянный диск для SQLite или Managed PostgreSQL) и не зависеть от «засыпания» free-тарифов.

### Деплой на Render (кратко)

1. Залейте проект на GitHub.
2. Render → New → Web Service → из репозитория.
3. Runtime: Docker (есть `Dockerfile`) **или** Native:
   - Build: `pip install -r requirements.txt`
   - Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Environment: все переменные из `.env` (`PUBLIC_BASE_URL` = URL сервиса Render).
5. В Robokassa укажите Result/Success/Fail на этот URL.

> На free-тарифе файл SQLite может сброситься при редеплое. Для боя: Persistent Disk на Render / том на Amvera / Yandex Object Storage не подойдёт для SQLite — лучше диск или Postgres.

### Деплой на Yandex Cloud

Удобный путь: **Serverless Container** или небольшая **VM** + Docker:

```bash
docker build -t access-bot .
docker run -p 8000:8000 --env-file .env access-bot
```

Перед контейнером положите заполненный `.env` или задайте переменные в консоли Cloud.

---

## Структура проекта

```
app/
  main.py          # FastAPI: Robokassa + webhook Telegram + страница успеха
  bot_handlers.py  # Логика /start и выдача invite-ссылки
  robokassa.py     # Проверка подписей
  db.py            # SQLite: оплаты и токены
  config.py        # Настройки из .env
  templates/       # Страница «Спасибо»
scripts/get_chat_id.py
Dockerfile
```

---

## Безопасность (коротко)

- Доступ выдаётся только по токену после оплаты.
- Токен и invite-ссылка — **одноразовые**; повторное использование блокируется.
- Не публикуйте `.env` и токен бота.
- После тестов отключите `/dev/*` через `ROBOKASSA_IS_TEST=0`.

---

## Что дальше (Max и доработки)

1. Вынести «выдачу доступа» в общий сервис; Telegram / Max — отдельные адаптеры.
2. При необходимости: PostgreSQL вместо SQLite, логирование оплат, уведомление админу о новых оплатах.
3. Кик неактивных / срок подписки — отдельная задача (бот уже админ чата).

Если нужно — следующим шагом могу помочь задеплоить на Render/Amvera или настроить Robokassa по вашим реальным URL.

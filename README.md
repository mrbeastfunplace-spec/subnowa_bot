# Subnowa Bot

Telegram-бот с PostgreSQL, мультиязычной клиентской частью и Telegram CMS для администрирования.

Запуск:

```bash
python app.py
```

## Что внутри

- PostgreSQL вместо SQLite
- клиентские языки: `ru`, `uz`, `en`
- Telegram CMS на русском
- динамические товары, оплаты, тексты и кнопки
- автоматическая выдача CapCut аккаунтов со склада
- ручная обработка ChatGPT и других заявок

## Структура

- `app.py` — обязательная точка входа
- `bot_app.py` — новый bootstrap приложения
- `db/` — модели, сессия, bootstrap, дефолтные сиды
- `services/` — бизнес-логика
- `handlers/` — клиентские роутеры
- `admin/` — админская Telegram CMS
- `payments/` — архитектура платёжных провайдеров
- `utils/` — утилиты

## Переменные окружения

```env
BOT_TOKEN=your_telegram_bot_token
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DBNAME
ADMIN_IDS=7716923294,123456789
SUPPORT_URL=https://t.me/subnowa_supportbot
ABOUT_URL=https://subnowa.site
REVIEW_URL=https://t.me/subbowaotzib
REQUIRED_CHANNEL=@your_channel
DEFAULT_LANGUAGE=ru
TRIAL_DURATION_DAYS=3
PAYMENT_WINDOW_HOURS=12
```

## Как подключить PostgreSQL

1. Создайте PostgreSQL базу.
2. Получите строку подключения.
3. Передайте её в `DATABASE_URL`.
4. При первом запуске бот сам создаст таблицы и стартовые данные.

Формат:

```env
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DBNAME
```

## Railway

1. Создайте проект на Railway.
2. Добавьте сервис PostgreSQL.
3. Возьмите connection string и приведите её к формату SQLAlchemy async:

```env
postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DBNAME
```

4. Добавьте все переменные окружения в Railway Variables.
5. Команда запуска:

```bash
python app.py
```

## Первый запуск

При старте приложение:

- создаёт таблицы PostgreSQL
- заполняет стартовые категории
- создаёт базовые товары
- создаёт стартовые тексты и layout-кнопки
- создаёт методы оплаты и связи с товарами

## Важно

- старый `bot.db` новой архитектурой не используется
- данные из SQLite не мигрируются
- проект рассчитан на чистую PostgreSQL базу
- для входа в CMS используйте `/admin`

## Установка

```bash
pip install -r requirements.txt
```

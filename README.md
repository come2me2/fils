# FILS Design — подбор дивана (Telegram Bot)

Минималистичный Telegram-бот-квиз для бренда дизайнерской мебели FILS DESIGN. Задача — вовлечь пользователя, подобрать диван по стилю жизни и собрать контакт для связи с дизайнером.

## Возможности
- Линейный квиз из 4 вопросов с логикой подбора модели.
- Поддержка Markdown и эмодзи, паузы 1.5–2 сек для плавности.
- Финальная рекомендация одной из 4 моделей: CLOUD, GOCCI, FLOUS, JUNGLE.
- **Автоматическая выдача персонального промокода на 5000₽** за прохождение квиза.
- Запрос контакта (номер телефона) по кнопке и пересылка заявки менеджеру (чат-ID).
- Админ-панель с управлением промокодами и статистикой.

## Быстрый старт
1) Установите зависимости:
```bash
pip install -r requirements.txt
```

2) Создайте `.env` файл с переменными:
```bash
# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=your_bot_token_here
MANAGER_CHAT_ID=123456789

# Database Configuration (Neon PostgreSQL)
DATABASE_URL=postgresql://username:password@hostname:port/database

# Webhook Security
TELEGRAM_WEBHOOK_SECRET=your_webhook_secret_here

# Admin Panel Security
ADMIN_SECRET=your_admin_password_here

# Message Delays (optional)
MESSAGE_DELAY_SECONDS=1.7
QUESTION_DELAY_SECONDS=0.0
RESULT_DELAY_SECONDS=0.2
```

3) Запустите бота:
```bash
python bot.py
```

## Деплой на Vercel (webhook)
Бот на Vercel работает как serverless webhook (без long polling).

1) Репозиторий уже подготовлен: `api/telegram.py` (FastAPI) и `vercel.json`.

2) Создайте проект на Vercel (через Dashboard или `vercel` CLI), подключив этот репозиторий.

3) В настройках проекта Vercel задайте переменные окружения:
   - `TELEGRAM_BOT_TOKEN`
   - `MANAGER_CHAT_ID`
   - `DATABASE_URL` — строка подключения к PostgreSQL
   - `TELEGRAM_WEBHOOK_SECRET` — секрет для проверки заголовка Telegram
   - `ADMIN_SECRET` — пароль для админ-панели
   - `MESSAGE_DELAY_SECONDS` (опц.)

4) После деплоя получите домен проекта, например: `https://your-project.vercel.app`.

5) Установите webhook в Telegram (подставьте свой домен и секрет):
```bash
curl -X POST \
  "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook" \
  -d url="https://your-project.vercel.app/api/telegram" \
  -d secret_token="$TELEGRAM_WEBHOOK_SECRET"
```

6) Проверьте здоровье эндпоинта:
```
https://your-project.vercel.app/api/health
```
Статус должен быть `{ "status": "ok" }`.

## Логика результатов (кратко)
- Комфорт / просторная гостиная / современный стиль → **CLOUD**
- Минимализм / квартира-студия / функциональность → **GOCCI**
- Лофт / офис / статус / чёткие формы → **FLOUS**
- Уют / семейный отдых / дом за городом → **JUNGLE**

## Структура
- `bot.py` — основной код бота (вопросы, логика, задержки, контакт, промокоды).
- `db.py` — работа с PostgreSQL базой данных и промокодами.
- `requirements.txt` — зависимости.
- `api/telegram.py` — FastAPI webhook для Vercel с админ-панелью.
- `vercel.json` — конфигурация функций и роутинга для Vercel.

## Заметки по эксплуатации
- Бот использует long polling. Для продакшена можно перевести на webhooks.
- Если `MANAGER_CHAT_ID` не задан, бот не будет отправлять заявку менеджеру (пользователь всё равно получит подтверждение).
- Ссылки на модели ведут на сайт FILS DESIGN:
  - CLOUD: https://filsdesign.ru/sofas/cloud
  - GOCCI: https://filsdesign.ru/sofas/gocci
  - FLOUS: https://filsdesign.ru/sofas/flous
  - JUNGLE: https://filsdesign.ru/sofas/jungle
  - Все модели: https://filsdesign.ru/sofas

## Система промокодов
- Каждый пользователь получает персональный промокод на 5000₽ за прохождение квиза
- Промокоды генерируются в формате `FILSXXXXXX` (6 случайных символов)
- Срок действия промокода: 1 год с момента выдачи
- Все промокоды сохраняются в базе данных с привязкой к пользователю
- Админ-панель позволяет просматривать все выданные промокоды и статистику

## Админ-панель
Доступна по адресу `/admin` после деплоя:
- **Пользователи** — список всех пользователей бота
- **Статистика** — общая статистика и данные по промокодам
- **Промокоды** — управление и просмотр всех выданных промокодов
- **Рассылки** — отправка сообщений всем пользователям

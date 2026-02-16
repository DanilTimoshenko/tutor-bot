# Деплой на Railway и постоянная база данных

## Первый запуск (если ещё не деплоил)

1. Зайди на [railway.app](https://railway.app), войди в аккаунт.
2. **New Project** → **Deploy from GitHub repo** → выбери репозиторий **DanilTimoshenko/tutor-bot** (или подключи GitHub, если ещё не подключён).
3. Railway подхватит проект (есть `requirements.txt`, `Procfile` с `worker: python main.py`).
4. Открой сервис → вкладка **Variables** и добавь переменные (см. таблицу ниже).
5. Обязательно: **BOT_TOKEN** (от @BotFather), **TUTOR_USER_ID** (твой Telegram ID). Остальные — по желанию.
6. Сохрани — деплой запустится сам. В логах (**Deployments** → последний деплой → **View Logs**) должно быть что-то вроде «Application started».

Если бот не отвечает: проверь, что в Variables нет опечаток и BOT_TOKEN совпадает с токеном бота в Telegram.

---

## Постоянная база данных (Volume)

Чтобы база (уроки, слоты, записи) **не сбрасывалась** при каждом Redeploy, нужно хранить её на **Volume**.

## Шаги в Railway

### 1. Добавить Volume к сервису tutor-bot

1. Открой свой проект в Railway → сервис **tutor-bot**.
2. Вкладка **Settings** (или в боковом меню сервиса найди раздел **Volumes**).
3. Нажми **Add Volume** / **New Volume**.
4. Укажи **Mount Path**: `/data` (или любой путь, например `/app/data`).
5. Сохрани.

### 2. Указать путь к базе переменной окружения

1. Вкладка **Variables** сервиса tutor-bot.
2. Добавь переменную:
   - **Name:** `DATABASE_PATH`
   - **Value:** `/data/tutor_bot.db`
3. Сохрани (если Mount Path был другой, подставь его: `ТВОЙ_MOUNT_PATH/tutor_bot.db`).

### 3. Перезапустить деплой

**Deployments** → у последнего деплоя три точки → **Redeploy**.

После этого файл базы будет лежать на Volume и сохранится при новых деплоях. Уроки, слоты и записи не пропадут.

---

## Переменные для Railway (напоминание)

| Переменная        | Обязательно | Пример              |
|-------------------|-------------|----------------------|
| `BOT_TOKEN`       | да          | токен от @BotFather  |
| `TUTOR_USER_ID`   | да          | твой Telegram ID    |
| `DATABASE_PATH`   | для Volume  | `/data/tutor_bot.db` |
| `YANDEX_API_KEY`   | для «Помощь с домашкой» | API-ключ Yandex Cloud |
| `YANDEX_FOLDER_ID` | для «Помощь с домашкой» | ID каталога в Yandex Cloud |
| `BOT_TITLE`       | нет         | название бота       |
| `MATERIALS_CHANNEL_LINK` | нет | ссылка на канал  |

# Бот для записи на уроки репетитора

Telegram-бот, через который ученики могут записываться на твои уроки.

## Возможности

**Для учеников:**
- Просмотр доступных уроков (`/lessons`)
- Запись на урок по кнопке
- Список своих записей (`/my`) и отмена записи

**Для репетитора (только твой Telegram ID):**
- Добавление уроков: дата, время, название (`/add_lesson`)
- Просмотр расписания и списка записанных (`/schedule`)
- Удаление уроков

Данные хранятся локально в SQLite (`tutor_bot.db`).

## Установка

1. Создай бота в Telegram: открой [@BotFather](https://t.me/BotFather), отправь `/newbot`, придумай имя и получи **токен**.

2. Узнай свой Telegram ID: напиши боту [@userinfobot](https://t.me/userinfobot) — он пришлёт твой ID.

3. Установи зависимости (на Mac часто нужны `python3` и виртуальное окружение):
   ```bash
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```

4. Настрой конфиг:
   ```bash
   cp config.example.py config.py
   ```
   Открой `config.py` и укажи:
   - `BOT_TOKEN` — токен от BotFather
   - `TUTOR_USER_ID` — твой Telegram ID (число)

5. Запуск:
   ```bash
   .venv/bin/python main.py
   ```
   Или: `./run.sh`

6. Запуск без терминала (в фоне):
   - Просто в фоне (логи в `bot.log`): `./run-background.sh`. Остановить: `./stop-bot.sh`.
   - Как служба (включится после входа в Mac, перезапуск при падении): скопировать `com.tutorbot.plist` в `~/Library/LaunchAgents/`, затем выполнить:
     ```bash
     cp com.tutorbot.plist ~/Library/LaunchAgents/
     launchctl load ~/Library/LaunchAgents/com.tutorbot.plist
     ```
     Остановить: `launchctl unload ~/Library/LaunchAgents/com.tutorbot.plist`

Дальше ученики могут найти бота по имени и записываться на уроки через команду `/lessons`.

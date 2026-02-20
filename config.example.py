# Скопируй этот файл в config.py и заполни свои данные
# Команда: cp config.example.py config.py

# Токен бота от @BotFather в Telegram
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

# Telegram ID администратора (только этот пользователь — админ; может добавлять репетиторов)
ADMIN_USER_ID = 123456789

# Telegram ID репетитора (для обратной совместимости = один репетитор). Или список репетиторов:
# TUTOR_USER_IDS = [123456789, 987654321]  # админ + другие репетиторы
TUTOR_USER_ID = 123456789
TUTOR_USER_IDS = None  # если None — считаем репетиторами только [TUTOR_USER_ID]; иначе список ID

# Название в приветствии (например "Timoshenko's Atelier"). Можно None
BOT_TITLE = None

# Имя репетитора в рассылке приглашений («Имя приглашает вас на занятие …»). None — «Репетитор»
TUTOR_DISPLAY_NAME = None

# Ссылка на канал с материалами для учеников. Команда /materials отправит её.
MATERIALS_CHANNEL_LINK = None

# Канал для анонсов новых уроков (бот должен быть админом). None — не постить.
CHANNEL_ID = None

# Час (0-23) ежедневной сводки репетитору. None — только по /summary
SUMMARY_DAILY_HOUR = 9

# Ссылка на урок: за 1 минуту до начала бот отправит её каждому записанному ученику. None — не отправлять.
LESSON_LINK = None

# Yandex GPT для «Помощь с домашкой». Без ключа и каталога кнопка не показывается.
# Каталог и API-ключ: Yandex Cloud → AI Foundation Models → подключаешь YandexGPT → смотри folder_id и создаёшь API-ключ.
YANDEX_API_KEY = None
YANDEX_FOLDER_ID = None

# Тег в Telegram для раздела ЕГЭ (показывается вместо ссылки на источник). Например: "@YourNick"
EGE_AUTHOR_TG = None

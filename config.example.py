# Скопируй этот файл в config.py и заполни свои данные
# Команда: cp config.example.py config.py

# Токен бота от @BotFather в Telegram
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

# Telegram ID репетитора (только этот пользователь может создавать уроки)
# Узнать свой ID: напиши боту @userinfobot в Telegram
TUTOR_USER_ID = 123456789

# Название в приветствии (например "Timoshenko's Atelier"). Можно None
BOT_TITLE = None

# Ссылка на канал с материалами для учеников. Команда /materials отправит её.
MATERIALS_CHANNEL_LINK = None

# Канал для анонсов новых уроков (бот должен быть админом). None — не постить.
CHANNEL_ID = None

# Час (0-23) ежедневной сводки репетитору. None — только по /summary
SUMMARY_DAILY_HOUR = 9

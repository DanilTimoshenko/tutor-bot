"""
Telegram-бот для записи учеников на уроки репетитора.
Запуск: python main.py
"""
import logging
from datetime import time as dt_time

from telegram import BotCommand, Update
from telegram.error import Conflict
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, TypeHandler, filters

from config_loader import config
import database as db
import handlers as h

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main() -> None:
    import re
    token = (config.BOT_TOKEN or "").strip()
    if not token:
        raise SystemExit(
            "Ошибка: BOT_TOKEN не задан. На Railway: сервис tutor-bot → Variables → "
            "добавь BOT_TOKEN (токен от @BotFather)."
        )
    # Формат токена Telegram: 123456789:ABCdef...
    if not re.match(r"^\d+:[A-Za-z0-9_-]{35,}$", token):
        raise SystemExit(
            "Ошибка: BOT_TOKEN не похож на токен от @BotFather (должен быть вида 123456789:AAH...). "
            "Проверь переменную BOT_TOKEN в Railway Variables — скопируй токен целиком, без пробелов."
        )
    try:
        app = Application.builder().token(token).build()
    except Exception as e:
        if "InvalidToken" in type(e).__name__ or "token" in str(e).lower():
            raise SystemExit(
                "Ошибка: Telegram не принял токен. Проверь в Railway Variables: "
                "имя переменной точно BOT_TOKEN, значение скопировано из @BotFather целиком (без кавычек и пробелов)."
            ) from e
        raise
    _tid = config.TUTOR_USER_ID
    _aid = getattr(config, "ADMIN_USER_ID", None) or _tid
    _tids = getattr(config, "TUTOR_USER_IDS", None)
    if _tids is None:
        _tids = {_tid}
    else:
        _tids = set(_tids) if not isinstance(_tids, set) else _tids
        if _aid not in _tids:
            _tids = set(_tids) | {_aid}
    app.bot_data["tutor_user_id"] = _tid
    app.bot_data["admin_user_id"] = _aid
    app.bot_data["tutor_user_ids"] = _tids
    app.bot_data["bot_title"] = getattr(config, "BOT_TITLE", None)
    app.bot_data["materials_channel_link"] = getattr(config, "MATERIALS_CHANNEL_LINK", None)
    _yandex_key = (getattr(config, "YANDEX_API_KEY", None) or "").strip()
    _yandex_folder = (getattr(config, "YANDEX_FOLDER_ID", None) or "").strip()
    app.bot_data["yandex_api_key"] = _yandex_key
    app.bot_data["yandex_folder_id"] = _yandex_folder
    app.bot_data["openai_api_key"] = _yandex_key and _yandex_folder
    app.bot_data["lesson_link"] = (getattr(config, "LESSON_LINK", None) or "").strip() or None
    app.bot_data["ege_author_tg"] = (getattr(config, "EGE_AUTHOR_TG", None) or "").strip() or None
    app.bot_data["tutor_display_name"] = (getattr(config, "TUTOR_DISPLAY_NAME", None) or "").strip() or "Репетитор"

    # Проверка подписки на канал (group=-1: выполняется первым)
    sub_channel = getattr(config, "SUBSCRIPTION_CHANNEL_ID", None)
    if sub_channel:
        app.add_handler(TypeHandler(Update, h.subscription_check), group=-1)

    app.add_handler(CommandHandler("start", h.start))
    app.add_handler(CommandHandler("help", h.help_cmd))
    app.add_handler(CommandHandler("lessons", h.lessons_list))
    app.add_handler(CommandHandler("my", h.my_bookings))
    app.add_handler(CommandHandler("materials", h.materials_cmd))
    app.add_handler(CommandHandler("add_lesson", h.add_lesson_start))
    app.add_handler(CommandHandler("schedule", h.schedule_tutor))
    app.add_handler(CommandHandler("summary", h.summary_cmd))
    app.add_handler(CommandHandler("clear_chat", h.clear_chat_cmd))
    app.add_handler(CallbackQueryHandler(h.button_callback))

    async def text_handler(update, context):
        if context.user_data.get("homework_help"):
            if await h.homework_receive(update, context):
                return
        if context.user_data.get("booking_username_input"):
            if await h.booking_username_receive(update, context):
                return
        if context.user_data.get("request_slot"):
            if await h.request_slot_receive(update, context):
                return
        if context.user_data.get("schedule_range_input"):
            if await h.schedule_range_receive(update, context):
                return
        if context.user_data.get("block_slot"):
            if await h.block_slot_receive(update, context):
                return
        if context.user_data.get("add_tutor_input"):
            if await h.add_tutor_receive(update, context):
                return
        if context.user_data.get("blocked_slot_link_input"):
            if await h.blocked_slot_link_receive(update, context):
                return
        if context.user_data.get("lesson_link_input"):
            if await h.lesson_link_receive(update, context):
                return
        if context.user_data.get("add_lesson"):
            await h.add_lesson_receive(update, context)
            return
        # Нет активного диалога — подсказка, чтобы не было «бот молчит»
        try:
            await update.message.reply_text(
                "Используйте кнопки меню ниже или нажмите /start для выбора действия."
            )
        except Exception:
            logger.exception("Не удалось отправить ответ пользователю")

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    async def on_error(update, context):
        error = context.error
        if isinstance(error, Conflict):
            logger.warning(
                "Conflict: другой экземпляр бота получает обновления. "
                "Ждём и повторим — не выключаем процесс, чтобы после остановки второго экземпляра этот подхватил обновления."
            )
        else:
            logger.exception("Update %s caused error %s", update, error)
            try:
                if update and update.effective_message:
                    await update.effective_message.reply_text(
                        "Произошла ошибка. Попробуй ещё раз или /start."
                    )
            except Exception:
                pass

    app.add_error_handler(on_error)

    async def post_init(application):
        await db.init_db()
        # Репетиторы из конфига + добавленные админом через бота
        extra_tutors = await db.get_tutor_user_ids_from_db()
        application.bot_data["tutor_user_ids"] = application.bot_data["tutor_user_ids"] | extra_tutors
        try:
            from set_ege_images_1_6 import ensure_ege_tasks_1_6
            await ensure_ege_tasks_1_6()
        except Exception as e:
            logger.warning("ЕГЭ 1–6: не удалось заполнить задания при старте: %s", e)
        me = await application.bot.get_me()
        application.bot_data["bot_username"] = me.username or ""
        application.bot_data["channel_id"] = getattr(config, "CHANNEL_ID", None)
        # В меню бота (когда пользователь нажимает /) — только команды для учеников.
        commands = [
            BotCommand("start", "Начать"),
            BotCommand("lessons", "Доступные уроки и запись"),
            BotCommand("my", "Мои записи"),
            BotCommand("help", "Справка"),
        ]
        if getattr(config, "MATERIALS_CHANNEL_LINK", None):
            commands.append(BotCommand("materials", "Материалы к урокам"))
        await application.bot.set_my_commands(commands)
        # Ежедневная сводка репетитору
        summary_hour = getattr(config, "SUMMARY_DAILY_HOUR", None)
        if summary_hour is not None and application.job_queue:
            application.job_queue.run_daily(
                h.daily_summary_callback,
                time=dt_time(hour=int(summary_hour), minute=0),
            )
        # За 1 минуту до урока — отправить ссылку записанным ученикам (если LESSON_LINK задан)
        if application.bot_data.get("lesson_link") and application.job_queue:
            application.job_queue.run_repeating(
                h.send_lesson_links_callback,
                interval=60,
                first=10,
            )
        logger.info("Database initialized.")

    app.post_init = post_init
    logger.info("Bot starting...")
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()

"""
Telegram-бот для записи учеников на уроки репетитора.
Запуск: python main.py
"""
import logging
from datetime import time as dt_time

from telegram import BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters

from config_loader import config
import database as db
import handlers as h

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main() -> None:
    app = Application.builder().token(config.BOT_TOKEN).build()
    app.bot_data["tutor_user_id"] = config.TUTOR_USER_ID
    app.bot_data["bot_title"] = getattr(config, "BOT_TITLE", None)
    app.bot_data["materials_channel_link"] = getattr(config, "MATERIALS_CHANNEL_LINK", None)

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
        if context.user_data.get("request_slot"):
            if await h.request_slot_receive(update, context):
                return
        if context.user_data.get("schedule_range_input"):
            if await h.schedule_range_receive(update, context):
                return
        if context.user_data.get("block_slot"):
            if await h.block_slot_receive(update, context):
                return
        if context.user_data.get("add_lesson"):
            await h.add_lesson_receive(update, context)
            return
        # Нет активного диалога — подсказка, чтобы не было «бот молчит»
        await update.message.reply_text(
            "Используйте кнопки меню ниже или нажмите /start для выбора действия."
        )

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    async def post_init(application):
        await db.init_db()
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
        logger.info("Database initialized.")

    app.post_init = post_init
    logger.info("Bot starting...")
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()

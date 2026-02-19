"""
Обработчики для администратора: выбор режима, добавить репетитора, скачать БД, как видят ученики.
"""
import io
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import ContextTypes

import database as db

from .common import (
    KEYBOARD_BACK_TO_MAIN,
    _build_main_menu_content,
    is_admin,
    is_tutor,
    MSG_ONLY_TUTOR,
)

logger = logging.getLogger(__name__)


async def handle_callback(query, context: ContextTypes.DEFAULT_TYPE, data: str, user_id: int) -> bool:
    if data == "choose_mode_admin":
        if not is_admin(user_id, context.bot_data):
            await query.answer("Доступно только администратору.")
            return True
        context.user_data["admin_mode"] = "admin"
        text, keyboard = _build_main_menu_content(
            user_id, query.from_user.first_name, context.bot_data, context.user_data
        )
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return True
    if data == "choose_mode_tutor":
        if not is_admin(user_id, context.bot_data):
            await query.answer("Доступно только администратору.")
            return True
        context.user_data["admin_mode"] = "tutor"
        text, keyboard = _build_main_menu_content(
            user_id, query.from_user.first_name, context.bot_data, context.user_data
        )
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return True
    if data == "choose_mode_student":
        if not is_admin(user_id, context.bot_data):
            await query.answer("Доступно только администратору.")
            return True
        context.user_data["admin_mode"] = "student"
        text, keyboard = _build_main_menu_content(
            user_id, query.from_user.first_name, context.bot_data, context.user_data
        )
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return True
    if data == "admin_add_tutor":
        if not is_admin(user_id, context.bot_data):
            await query.edit_message_text(MSG_ONLY_TUTOR)
            return True
        await query.edit_message_text(
            "➕ Добавить репетитора\n\n"
            "Репетиторов задают в настройках (Railway Variables или config.py).\n\n"
            "Переменная TUTOR_USER_IDS — перечисли ID через запятую, например: 2071587097,123456789\n"
            "После изменения сделай Redeploy.",
            reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN),
        )
        return True
    if data == "admin_download_db":
        if not is_admin(user_id, context.bot_data):
            await query.edit_message_text("Скачать БД может только администратор.")
            return True
        try:
            path = db.DB_PATH
            if not path.exists():
                await query.edit_message_text(
                    "📥 Файл базы данных ещё не создан.",
                    reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN),
                )
                return True
            with open(path, "rb") as f:
                data_bytes = f.read()
            await query.edit_message_text("📥 Отправляю файл базы данных…")
            await context.bot.send_document(
                chat_id=query.message.chat_id,
                document=InputFile(io.BytesIO(data_bytes), filename="tutor_bot.db"),
                caption="Резервная копия базы.",
            )
            await query.edit_message_text(
                "✅ Файл отправлен в чат.",
                reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN),
            )
        except Exception as e:
            logger.exception("admin_download_db: %s", e)
            await query.edit_message_text(
                f"❌ Не удалось отправить базу: {e}.",
                reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN),
            )
        return True
    if data == "tutor_preview_student":
        if not is_admin(user_id, context.bot_data):
            await query.edit_message_text("Доступно только администратору.")
            return True
        title = context.bot_data.get("bot_title") or "Репетитор"
        preview_text = (
            f"👋 Привет, друг!\n\nЯ бот записи на уроки — {title}.\n\nВыберите действие:"
        )
        keyboard = [
            [InlineKeyboardButton("📅 Записаться на урок", callback_data="student_lessons")],
            [InlineKeyboardButton("📌 Мои записи и слоты", callback_data="student_my")],
            [InlineKeyboardButton("🕐 Записаться на свободное время", callback_data="student_freetime")],
            [InlineKeyboardButton("👤 Репетитор", callback_data="student_tutor")],
        ]
        if context.bot_data.get("openai_api_key"):
            keyboard.append([InlineKeyboardButton("AITimoshenko'sAtelie", callback_data="student_homework_help")])
        keyboard.append([InlineKeyboardButton("📚 Раздел ЕГЭ", callback_data="student_ege")])
        await query.message.reply_text("👀 Так видят ученики:\n━━━━━━━━━━━━━━━━━━━━")
        await context.bot.send_message(
            chat_id=user_id,
            text=preview_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return True
    return False

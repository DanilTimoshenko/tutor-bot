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
    _clear_other_flows,
    is_admin,
    is_tutor,
    MSG_ONLY_TUTOR,
)

logger = logging.getLogger(__name__)


async def add_tutor_receive(update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Обработка ввода Telegram ID нового репетитора (админ). Возвращает True если обработано."""
    if not context.user_data.get("add_tutor_input"):
        return False
    user_id = update.effective_user.id
    if not is_admin(user_id, context.bot_data):
        context.user_data.pop("add_tutor_input", None)
        return True
    text = (update.message.text or "").strip()
    if text.lower() in ("отмена", "отменить", "cancel"):
        context.user_data.pop("add_tutor_input", None)
        await update.message.reply_text(
            "Добавление репетитора отменено.",
            reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN),
        )
        return True
    try:
        new_id = int(text)
    except ValueError:
        await update.message.reply_text(
            "❌ Введите число (Telegram ID). Узнать ID можно у @userinfobot. Или напишите «отмена»."
        )
        return True
    if new_id <= 0:
        await update.message.reply_text("❌ ID должен быть положительным числом.")
        return True
    ok = await db.add_tutor_user_id(new_id)
    context.user_data.pop("add_tutor_input", None)
    if ok:
        context.bot_data.setdefault("tutor_user_ids", set()).add(new_id)
        await update.message.reply_text(
            f"✅ Готово. Пользователь с ID {new_id} теперь репетитор — при /start увидит меню репетитора.",
            reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN),
        )
    else:
        await update.message.reply_text(
            "Репетитор с таким ID уже был добавлен ранее.",
            reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN),
        )
    return True


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
        _clear_other_flows(context, "add_tutor_input")
        context.user_data["add_tutor_input"] = True
        await query.edit_message_text(
            "➕ Добавить репетитора\n\n"
            "Введите Telegram ID нового репетитора (число).\n"
            "Узнать ID: пусть человек напишет боту @userinfobot — тот пришлёт ID.\n\n"
            "Напишите «отмена», чтобы выйти.",
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

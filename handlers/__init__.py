"""
Пакет обработчиков бота. Точка входа — button_callback и команды.
"""
import logging
from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from . import common
from . import student
from . import ege
from . import schedule
from . import tutor
from . import admin

logger = logging.getLogger(__name__)

# Публичный API для main.py
FLOW_KEYS = common.FLOW_KEYS
KEYBOARD_BACK_TO_MAIN = common.KEYBOARD_BACK_TO_MAIN

start = common.start
help_cmd = common.help_cmd
materials_cmd = common.materials_cmd
clear_chat_cmd = common.clear_chat_cmd

lessons_list = student.lessons_list
my_bookings = student.my_bookings
homework_receive = student.homework_receive
request_slot_receive = student.request_slot_receive
booking_username_receive = student.booking_username_receive

schedule_tutor = schedule.schedule_tutor
schedule_range_receive = schedule.schedule_range_receive
block_slot_receive = schedule.block_slot_receive
blocked_slot_link_receive = schedule.blocked_slot_link_receive
lesson_link_receive = schedule.lesson_link_receive

add_lesson_start = tutor.add_lesson_start
add_lesson_receive = tutor.add_lesson_receive
summary_cmd = tutor.summary_cmd
daily_summary_callback = tutor.daily_summary_callback
send_lesson_links_callback = tutor.send_lesson_links_callback

add_tutor_receive = admin.add_tutor_receive
subscription_check = common.subscription_check


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    data = query.data or ""
    user_id = query.from_user.id

    # Защита от двойных нажатий: один callback_data + message_id обрабатываем только раз
    unique_cbq = data + "_" + (str(query.message.message_id) if query.message else "")
    if context.user_data.get("last_cbq") == unique_cbq:
        try:
            await query.answer()
        except Exception:
            pass
        return
    context.user_data["last_cbq"] = unique_cbq

    try:
        await query.answer()
    except Exception as e:
        logger.warning("query.answer failed: %s", e)

    try:
        # Главное меню
        if data == "main_menu":
            for key in FLOW_KEYS:
                context.user_data.pop(key, None)
            user = query.from_user
            text, keyboard = common._build_main_menu_content(
                user.id, user.first_name, context.bot_data, context.user_data
            )
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return

        # Репетитор: войти в режим тестового ученика
        if data == "tutor_view_as_student":
            if not common.is_tutor(user_id, context.bot_data):
                await query.edit_message_text(common.MSG_ONLY_TUTOR)
                return
            context.user_data["view_as_student"] = True
            text, keyboard = common._build_main_menu_content(
                user_id, query.from_user.first_name, context.bot_data, context.user_data
            )
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return

        # Выйти из режима тестового ученика
        if data == "tutor_exit_test_student":
            context.user_data.pop("view_as_student", None)
            text, keyboard = common._build_main_menu_content(
                user_id, query.from_user.first_name, context.bot_data, context.user_data
            )
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return

        # Маршрутизация по модулям
        if await admin.handle_callback(query, context, data, user_id):
            return
        if await student.handle_callback(query, context, data, user_id):
            return
        if await ege.handle_callback(query, context, data, user_id):
            return
        if await schedule.handle_callback(query, context, data, user_id):
            return
        if await tutor.handle_callback(query, context, data, user_id):
            return

        # Неизвестный callback — показываем главное меню
        logger.warning("Unknown callback_data: %r", data)
        user = query.from_user
        text, keyboard = common._build_main_menu_content(
            user.id, user.first_name, context.bot_data, context.user_data
        )
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    except Exception as e:
        logger.exception("Callback error: %s", e)
        try:
            user = query.from_user
            text, keyboard = common._build_main_menu_content(
                user.id, user.first_name, context.bot_data, context.user_data
            )
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception:
            pass

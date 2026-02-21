"""
Обработчики для ученика: уроки, записи, свободное время, помощь с домашкой.
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import database as db
import homework_llm

from .common import (
    FLOW_KEYS,
    KEYBOARD_BACK_TO_MAIN,
    SCHEDULE_TEXT_MAX,
    DAY_NAMES,
    _clear_other_flows,
    _latex_to_plain,
    _format_homework_reply_for_telegram,
    format_lesson,
    parse_date,
    parse_time,
)

logger = logging.getLogger(__name__)

_LESSONS_LIST_MAX = 40


async def _build_my_bookings_message(user_id: int, username: str):
    """Возвращает (text, keyboard) для «Мои записи» ученика."""
    bookings = await db.get_my_bookings(user_id)
    assigned_slots = await db.get_blocked_slots_for_student(username) if username else []
    if not bookings and not assigned_slots:
        return None, None
    text = "📌 Ваши записи\n\n"
    keyboard = []
    if bookings:
        text += "Уроки:\n\n" + "\n\n".join(format_lesson(l) for l in bookings) + "\n\n"
        for l in bookings:
            keyboard.append([
                InlineKeyboardButton(
                    f"❌ Отменить урок · {l['title']} ({l['lesson_date']})",
                    callback_data=f"cancel_{l['id']}",
                ),
            ])
    if assigned_slots:
        text += "🔒 Закреплённые за вами слоты:\n\n"
        for s in assigned_slots:
            day = DAY_NAMES[s["day_of_week"]]
            text += f"   • {day} {s['lesson_time']} — {s['student_name']}\n"
        text += "\n"
        for s in assigned_slots:
            day = DAY_NAMES[s["day_of_week"]]
            keyboard.append([
                InlineKeyboardButton(
                    f"🔓 Отменить слот · {day} {s['lesson_time']}",
                    callback_data=f"student_unblock_{s['id']}",
                ),
            ])
    keyboard.extend(KEYBOARD_BACK_TO_MAIN)
    return text.strip(), InlineKeyboardMarkup(keyboard)


async def lessons_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        lessons = await db.get_upcoming_lessons(limit=_LESSONS_LIST_MAX + 1)
        if not lessons:
            await update.message.reply_text(
                "📭 Пока нет доступных уроков.\n\nСледи за обновлениями — новые слоты появятся здесь.",
            )
            return
        show = lessons[: _LESSONS_LIST_MAX]
        text = "📋 Доступные уроки\n\nВыбери урок и нажми кнопку записи:\n\n" + "\n\n".join(format_lesson(l) for l in show)
        if len(text) > SCHEDULE_TEXT_MAX:
            text = text[: SCHEDULE_TEXT_MAX - 80] + "\n\n… (показаны не все уроки)"
        if len(lessons) > _LESSONS_LIST_MAX:
            text += f"\n\n(показано {len(show)} из {len(lessons)} уроков)"
        keyboard = []
        for l in show:
            if (l.get("booked_count") or 0) < (l.get("max_students") or 1):
                btn_label = f"✏️ · {l.get('title', 'Урок')} ({l.get('lesson_date', '')} {l.get('lesson_time', '')})"
                if len(btn_label) > 60:
                    btn_label = btn_label[:57] + "…"
                keyboard.append([InlineKeyboardButton(btn_label, callback_data=f"book_{l['id']}")])
        if not keyboard:
            await update.message.reply_text(text)
            return
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        logger.exception("lessons_list: %s", e)
        try:
            await update.message.reply_text("Не удалось загрузить список уроков. Попробуй ещё раз или /start.")
        except Exception:
            pass


async def booking_username_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Обрабатывает ввод @username при записи на урок (если у пользователя нет username в Telegram)."""
    data = context.user_data.get("booking_username_input")
    if not data:
        return False
    text = (update.message.text or "").strip()
    if text.lower() in ("отмена", "отменить", "cancel"):
        context.user_data.pop("booking_username_input", None)
        await update.message.reply_text("Запись отменена.", reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN))
        return True
    username = text.strip().lstrip("@")
    if not username or len(username) < 2:
        await update.message.reply_text(
            "Укажите ваш @username в Telegram (например @ivanov) или напишите «отмена».",
        )
        return True
    lesson_id = data["lesson_id"]
    context.user_data.pop("booking_username_input", None)
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name
    ok, msg = await db.book_lesson(lesson_id, user_id, username=username, first_name=first_name)
    await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN))
    if ok:
        await db.update_blocked_slots_user_id(username, user_id)
        lesson = await db.get_lesson(lesson_id)
        tutor_id = context.bot_data.get("tutor_user_id")
        tutor_ids = context.bot_data.get("tutor_user_ids") or {tutor_id} if tutor_id else set()
        if lesson and tutor_ids:
            student_name = first_name or username or f"ID{user_id}"
            notify = f"🔔 Новая запись на урок\n\n👤 {student_name} @{username}\n\n▫️ {lesson['title']}\n📅 {lesson['lesson_date']}  ·  🕐 {lesson['lesson_time']}"
            for tid in tutor_ids:
                try:
                    await context.bot.send_message(chat_id=tid, text=notify)
                except Exception:
                    pass
    return True


async def my_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    username = (update.effective_user.username or "").strip()
    text, reply_markup = await _build_my_bookings_message(user_id, username)
    if text is None:
        await update.message.reply_text(
            "📌 У вас пока нет записей.\n\nНажми /lessons или кнопку «Записаться на урок».",
        )
        return
    await update.message.reply_text(text, reply_markup=reply_markup)


async def homework_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not context.user_data.get("homework_help"):
        return False
    text = (update.message.text or update.message.caption or "").strip()
    photo = update.message.photo
    image_bytes = None
    if photo:
        try:
            largest = photo[-1]
            tg_file = await context.bot.get_file(largest.file_id)
            image_bytes = bytes(await tg_file.download_as_bytearray())
        except Exception as e:
            logger.warning("homework_receive: failed to download photo: %s", e)
            await update.message.reply_text("Не удалось загрузить фото. Попробуй ещё раз или напиши текстом.")
            return True
    if not image_bytes and len(text) < 2:
        await update.message.reply_text("Напиши вопрос или задание текстом, либо пришли фото с заданием.")
        return True
    api_key = context.bot_data.get("yandex_api_key") or ""
    folder_id = context.bot_data.get("yandex_folder_id") or ""
    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        reply = await homework_llm.ask_homework(text, api_key, folder_id, image_bytes=image_bytes)
    except Exception as e:
        logger.exception("homework_receive: %s", e)
        await update.message.reply_text("Произошла ошибка при запросе. Попробуй ещё раз или /start.")
        await update.message.reply_text("💬 Задай следующий вопрос или /start — вернуться в меню.")
        return True
    if reply == homework_llm.OCR_FAILED:
        await update.message.reply_text(
            "Не удалось распознать текст на фото. Напиши задание текстом или пришли более чёткое фото."
        )
    elif reply:
        reply = _latex_to_plain(reply)
        if len(reply) > 4000:
            reply = reply[:3990] + "\n\n… (ответ обрезан)"
        body, parse_mode = _format_homework_reply_for_telegram(reply)
        await update.message.reply_text(body, parse_mode=parse_mode)
    else:
        if api_key and folder_id:
            await update.message.reply_text(
                "Не удалось получить ответ от Yandex GPT. Попробуй позже — репетитор может посмотреть логи."
            )
        else:
            await update.message.reply_text(
                "Не удалось получить ответ. Проверь, что у репетитора заданы YANDEX_API_KEY и YANDEX_FOLDER_ID."
            )
    await update.message.reply_text("💬 Задай следующий вопрос или /start — вернуться в меню.")
    return True


async def request_slot_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    data = context.user_data.get("request_slot")
    if not data:
        return False
    text = (update.message.text or "").strip()
    step = data.get("step")
    user = update.effective_user
    tutor_id = context.bot_data["tutor_user_id"]

    if step == "date":
        date = parse_date(text)
        if not date:
            await update.message.reply_text("❌ Неверный формат. Пример: 20.02.2025 или 2025-02-20")
            return True
        data["date"] = date
        data["step"] = "time"
        await update.message.reply_text("Напиши удобное время (например 14:00):")
        return True

    if step == "time":
        time = parse_time(text)
        if not time:
            await update.message.reply_text("❌ Неверный формат. Пример: 14:00")
            return True
        context.user_data.pop("request_slot", None)
        student_name = user.first_name or user.username or f"ID{user.id}"
        await db.add_free_time_request(
            user.id, user.username or "", user.first_name or "", data["date"], time,
        )
        req = f"🕐 Запрос на свободное время\n\n👤 {student_name}"
        if user.username:
            req += f" @{user.username}"
        req += f"\n\nЖелаемые дата и время: {data['date']} в {time}\n\nСоздайте урок в /add_lesson — тогда он появится у ученика в «Записаться на урок»."
        try:
            await context.bot.send_message(chat_id=tutor_id, text=req)
        except Exception:
            pass
        admin_id = context.bot_data.get("admin_user_id")
        if admin_id and admin_id != tutor_id:
            try:
                await context.bot.send_message(chat_id=admin_id, text=req)
            except Exception:
                pass
        await update.message.reply_text(
            "✅ Запрос отправлен репетитору.\n\n"
            "Когда урок будет создан, он появится в разделе «Записаться на урок» — зайди туда и запишись.",
        )
        return True
    return False


async def handle_callback(query, context: ContextTypes.DEFAULT_TYPE, data: str, user_id: int) -> bool:
    """Обрабатывает коллбэки student_*, book_, cancel_, student_unblock_. Возвращает True если обработано."""
    from .common import _build_main_menu_content, KEYBOARD_BACK_TO_MAIN, format_lesson

    tutor_id = context.bot_data["tutor_user_id"]

    if data == "student_lessons":
        lessons = await db.get_upcoming_lessons(limit=_LESSONS_LIST_MAX + 1)
        if not lessons:
            await query.edit_message_text(
                "📭 Пока нет доступных уроков.\n\nСледи за обновлениями.",
                reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN),
            )
            return True
        show = lessons[: _LESSONS_LIST_MAX]
        text = "📋 Доступные уроки\n\nВыбери урок и нажми кнопку записи:\n\n" + "\n\n".join(format_lesson(l) for l in show)
        if len(text) > SCHEDULE_TEXT_MAX:
            text = text[: SCHEDULE_TEXT_MAX - 80] + "\n\n… (показаны не все уроки)"
        if len(lessons) > _LESSONS_LIST_MAX:
            text += f"\n\n(показано {len(show)} из {len(lessons)} уроков)"
        keyboard = []
        for l in show:
            if (l.get("booked_count") or 0) < (l.get("max_students") or 1):
                btn_label = f"✏️ · {l.get('title', 'Урок')} ({l.get('lesson_date', '')} {l.get('lesson_time', '')})"
                if len(btn_label) > 60:
                    btn_label = btn_label[:57] + "…"
                keyboard.append([InlineKeyboardButton(btn_label, callback_data=f"book_{l['id']}")])
        keyboard.append(KEYBOARD_BACK_TO_MAIN[0])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return True

    if data == "student_my":
        username = (query.from_user.username or "").strip()
        text, reply_markup = await _build_my_bookings_message(user_id, username)
        if text is None:
            await query.edit_message_text(
                "📌 У вас пока нет записей.\n\nНажми «Записаться на урок».",
                reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN),
            )
            return True
        await query.edit_message_text(text, reply_markup=reply_markup)
        return True

    if data == "student_tutor":
        title = context.bot_data.get("bot_title") or "Репетитор"
        msg = f"👤 Репетитор\n\nЗанятия ведёт: {title}."
        if context.bot_data.get("materials_channel_link"):
            msg += "\n\n📚 Материалы: /materials"
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN))
        return True

    if data == "student_freetime":
        _clear_other_flows(context, "request_slot")
        context.user_data["request_slot"] = {"step": "date"}
        await query.edit_message_text(
            "🕐 Запись на свободное время\n\n"
            "Напиши желаемую дату урока в формате 20.02.2025 или 2025-02-20:",
        )
        return True

    if data == "student_homework_help":
        _clear_other_flows(context, "homework_help")
        context.user_data["homework_help"] = True
        await query.edit_message_text(
            "AITimoshenko'sAtelie\n\n"
            "Напиши вопрос или пришли фото с заданием — постараюсь объяснить и подсказать ход решения.\n\n"
            "Для выхода нажми кнопку ниже или /start.",
            reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN),
        )
        return True

    if data.startswith("book_"):
        lesson_id = int(data.split("_")[1])
        username = (query.from_user.username or "").strip()
        if not username:
            _clear_other_flows(context, "booking_username_input")
            context.user_data["booking_username_input"] = {"lesson_id": lesson_id}
            await query.edit_message_text(
                "✏️ Укажите ваш @username в Telegram (например @ivanov).\n\nНапишите «отмена», чтобы отменить запись.",
                reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN),
            )
            return True
        ok, msg = await db.book_lesson(
            lesson_id, user_id,
            username=username,
            first_name=query.from_user.first_name,
        )
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN))
        if ok and username:
            await db.update_blocked_slots_user_id(username, user_id)
        if ok:
            lesson = await db.get_lesson(lesson_id)
            if lesson:
                student_name = query.from_user.first_name or username or f"ID{user_id}"
                notify = f"🔔 Новая запись на урок\n\n👤 {student_name}"
                if username:
                    notify += f" @{username}"
                notify += f"\n\n▫️ {lesson['title']}\n📅 {lesson['lesson_date']}  ·  🕐 {lesson['lesson_time']}"
                tutor_ids = context.bot_data.get("tutor_user_ids") or {tutor_id}
                for tid in tutor_ids:
                    try:
                        await context.bot.send_message(chat_id=tid, text=notify)
                    except Exception:
                        pass
        return True

    if data.startswith("student_unblock_"):
        slot_id = int(data.split("_")[2])
        slot = await db.get_blocked_slot_by_id(slot_id)
        if not slot:
            await query.edit_message_text("Слот уже снят.", reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN))
            return True
        student_username = (slot.get("student_username") or "").strip().lower()
        my_username = (query.from_user.username or "").strip().lower()
        if student_username and student_username != my_username:
            await query.edit_message_text("Этот слот закреплён за другим учеником.", reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN))
            return True
        await db.delete_blocked_slot(slot_id)
        username = (query.from_user.username or "").strip()
        text, reply_markup = await _build_my_bookings_message(user_id, username)
        if text is None:
            await query.edit_message_text(
                "✅ Слот отменён.\n\n📌 У вас больше нет записей.",
                reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN),
            )
            return True
        await query.edit_message_text("✅ Слот отменён.\n\n" + text, reply_markup=reply_markup)
        return True

    if data.startswith("cancel_"):
        lesson_id = int(data.split("_")[1])
        lesson = await db.get_lesson(lesson_id)
        ok, msg = await db.cancel_booking(lesson_id, user_id)
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN))
        if ok and lesson:
            student_name = query.from_user.first_name or query.from_user.username or f"ID{user_id}"
            notify = f"❌ Отмена записи\n\n👤 {student_name}"
            if query.from_user.username:
                notify += f" @{query.from_user.username}"
            notify += f" отменил(а) запись на урок\n\n▫️ {lesson.get('title', 'Урок')}\n📅 {lesson.get('lesson_date', '')}  ·  🕐 {lesson.get('lesson_time', '')}"
            tutor_ids = context.bot_data.get("tutor_user_ids") or {tutor_id}
            for tid in tutor_ids:
                try:
                    await context.bot.send_message(chat_id=tid, text=notify)
                except Exception:
                    pass
        return True

    return False

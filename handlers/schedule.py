"""
Расписание репетитора: просмотр, период, слоты, ссылки на уроки.
"""
import logging
from datetime import datetime, timedelta
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import database as db

from .common import (
    FLOW_KEYS,
    KEYBOARD_BACK_TO_MAIN,
    SCHEDULE_TEXT_MAX,
    SCHEDULE_LESSONS_BUTTONS,
    DAY_NAMES,
    DAY_NAMES_FULL,
    MSG_ONLY_TUTOR,
    _clear_other_flows,
    is_tutor,
    parse_date,
    parse_time,
    parse_day_of_week,
    normalize_slot_time,
)

logger = logging.getLogger(__name__)

# Корень проекта (handlers/schedule.py -> parent.parent)
_ROOT = Path(__file__).resolve().parent.parent


def _format_date_header(lesson_date: str) -> str:
    d = datetime.strptime(lesson_date, "%Y-%m-%d").date()
    return f"{DAY_NAMES_FULL[d.weekday()].capitalize()}, {d.strftime('%d.%m.%Y')}"


async def _build_schedule_message(context: ContextTypes.DEFAULT_TYPE):
    """Возвращает (text, keyboard) для экрана расписания."""
    user_data = (getattr(context, "user_data", None) or {}) if context else {}
    range_dates = user_data.get("schedule_range")
    today = datetime.now().strftime("%Y-%m-%d")
    to_7 = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    if range_dates:
        from_date, to_date = range_dates
        lessons = await db.get_lessons_in_range(from_date, to_date)
        d1 = datetime.strptime(from_date, "%Y-%m-%d").strftime("%d.%m.%Y")
        d2 = datetime.strptime(to_date, "%Y-%m-%d").strftime("%d.%m.%Y")
        period_label = f"{d1} — {d2}"
    else:
        from_date, to_date = today, to_7
        lessons = await db.get_lessons_in_range(from_date, to_date)
        period_label = f"{datetime.strptime(today, '%Y-%m-%d').strftime('%d.%m.%Y')} — {datetime.strptime(to_7, '%Y-%m-%d').strftime('%d.%m.%Y')} (7 дней)"
    blocked = await db.get_all_blocked_slots()
    text = "📅 Расписание"
    if period_label:
        text += f" ({period_label})\n\n"
    else:
        text += "\n\n"
    if lessons:
        text += "У каждого урока: 👥 Кто записан, 🗑 Удалить, 🔗 Ссылка.\n\n"
        by_key = {}
        for l in lessons:
            key = (l["title"], (l.get("lesson_time") or "").strip())
            by_key.setdefault(key, []).append(l)
        for (title, lt), group in sorted(by_key.items(), key=lambda x: (min(l["lesson_date"] for l in x[1]), x[0][1])):
            dates_fmt = [datetime.strptime(l["lesson_date"], "%Y-%m-%d").strftime("%d.%m") for l in sorted(group, key=lambda x: x["lesson_date"])]
            n = len(group)
            dates_str = ", ".join(dates_fmt[:3]) + (f" … ещё {n - 3} (всего {n})" if n > 5 else ", ".join(dates_fmt[3:]) if n > 3 else ", ".join(dates_fmt))
            if n <= 5:
                dates_str = ", ".join(dates_fmt)
            text += f"▫️ {title} · {lt}\n   📅 {dates_str}\n\n"
        text += f"Всего уроков: {len(lessons)}\n\n"
    else:
        text += "Уроков пока нет.\n\nНиже — закреплённые слоты.\n\n"
    if blocked:
        by_day = {}
        for b in blocked:
            by_day.setdefault(b["day_of_week"], []).append(b)
        text += "\n\n🔒 Занятые слоты:\n\n"
        for dow in sorted(by_day.keys()):
            text += f"——— {DAY_NAMES_FULL[dow].capitalize()} ———\n"
            by_time = {}
            for b in by_day[dow]:
                key = normalize_slot_time(b.get("lesson_time", "") or "")
                by_time.setdefault(key, []).append(b)
            for lt in sorted(by_time.keys()):
                names = ", ".join(s["student_name"] for s in by_time[lt])
                text += f"   • {DAY_NAMES[dow]} {lt} — {names}\n"
            text += "\n"
    if len(text) > SCHEDULE_TEXT_MAX:
        text = text[: SCHEDULE_TEXT_MAX - 50] + "\n\n… (задайте период)"
    keyboard = []
    for l in lessons[: SCHEDULE_LESSONS_BUTTONS]:
        date_short = datetime.strptime(l["lesson_date"], "%Y-%m-%d").strftime("%d.%m") if l.get("lesson_date") else ""
        keyboard.append([
            InlineKeyboardButton(f"👥 {date_short} {l.get('lesson_time', '')}", callback_data=f"tutor_bookings_{l['id']}"),
            InlineKeyboardButton("🗑 Удалить", callback_data=f"tutor_del_{l['id']}"),
            InlineKeyboardButton("🔗 Ссылка", callback_data=f"tutor_lesson_link_{l['id']}"),
        ])
    if len(lessons) > SCHEDULE_LESSONS_BUTTONS:
        keyboard.append([InlineKeyboardButton("… ещё уроков — задайте период", callback_data="tutor_schedule_set_range")])
    for b in blocked:
        day = DAY_NAMES[b["day_of_week"]]
        keyboard.append([
            InlineKeyboardButton(f"🔓 Снять · {b['student_name']} ({day} {b['lesson_time']})", callback_data=f"unblock_{b['id']}"),
            InlineKeyboardButton("🔗 Ссылка", callback_data=f"blocked_slot_link_{b['id']}"),
        ])
    keyboard.append([InlineKeyboardButton("🔒 Закрепить слот за учеником", callback_data="tutor_block_slot")])
    keyboard.append([
        InlineKeyboardButton("📅 Задать период", callback_data="tutor_schedule_set_range"),
        InlineKeyboardButton("След. 7 дней", callback_data="tutor_schedule_clear_range"),
    ])
    keyboard.append([
        InlineKeyboardButton("🗑 Удалить все уроки", callback_data="tutor_clear_lessons_only"),
        InlineKeyboardButton("🗑 Очистить всё (и слоты)", callback_data="tutor_clear_schedule"),
    ])
    keyboard.extend(KEYBOARD_BACK_TO_MAIN)
    return text, InlineKeyboardMarkup(keyboard)


async def _refresh_schedule_message(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    text, reply_markup = await _build_schedule_message(context)
    if len(text) > 4090:
        text = text[:4080] + "\n\n… (задайте период)"
    await query.edit_message_text(text, reply_markup=reply_markup)


async def schedule_tutor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_tutor(update.effective_user.id, context.bot_data):
        await update.message.reply_text(MSG_ONLY_TUTOR)
        return
    text, reply_markup = await _build_schedule_message(context)
    if len(text) > SCHEDULE_TEXT_MAX:
        text = text[: SCHEDULE_TEXT_MAX] + "\n\n… (задайте период в боте)"
    try:
        await update.message.reply_text(text, reply_markup=reply_markup)
    except Exception as e:
        logger.warning("schedule_tutor reply_text failed: %s", e)
        await update.message.reply_text(
            "Расписание слишком большое. Нажми «Расписание» в меню и выбери «📅 Задать период».",
        )


async def schedule_range_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    data = context.user_data.get("schedule_range_input")
    if not data:
        return False
    text = (update.message.text or "").strip()
    step = data.get("step")
    if step == "from":
        from_date = parse_date(text)
        if not from_date:
            await update.message.reply_text("❌ Неверный формат. Пример: 20.02.2025")
            return True
        data["from_date"] = from_date
        data["step"] = "to"
        await update.message.reply_text("📅 Шаг 2/2 · Конечная дата (ДД.ММ.ГГГГ):")
        return True
    if step == "to":
        to_date = parse_date(text)
        if not to_date:
            await update.message.reply_text("❌ Неверный формат. Пример: 27.02.2025")
            return True
        if to_date < data["from_date"]:
            await update.message.reply_text("❌ Конечная дата должна быть не раньше начальной.")
            return True
        context.user_data["schedule_range"] = (data["from_date"], to_date)
        context.user_data.pop("schedule_range_input", None)
        text_msg, reply_markup = await _build_schedule_message(context)
        await update.message.reply_text(text_msg, reply_markup=reply_markup)
        return True
    return False


async def block_slot_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    data = context.user_data.get("block_slot")
    if not data:
        return False
    text = (update.message.text or "").strip()
    if text.lower() in ("отмена", "отменить", "cancel"):
        context.user_data.pop("block_slot", None)
        await update.message.reply_text("Закрепление слота отменено.")
        return True
    step = data.get("step")
    if step == "name":
        data["student_name"] = text
        data["step"] = "day"
        await update.message.reply_text("🔒 Шаг 2/4 · День недели: пн, вт, ср, чт, пт, сб или вс")
        return True
    if step == "day":
        day = parse_day_of_week(text)
        if day is None:
            await update.message.reply_text("❌ Напиши: пн, вт, ср, чт, пт, сб или вс")
            return True
        data["day_of_week"] = day
        data["step"] = "time"
        await update.message.reply_text("🔒 Шаг 3/4 · Время (например 19:00)")
        return True
    if step == "time":
        time = parse_time(text)
        if not time:
            await update.message.reply_text("❌ Пример: 19:00")
            return True
        data["time"] = time
        if data.get("student_username") is not None:
            ok, msg = await db.add_blocked_slot(
                data["student_name"], data["day_of_week"], data["time"],
                student_username=data["student_username"],
            )
            data["slots_added"] = data.get("slots_added", 0) + 1
            data["step"] = "more_slot"
            await update.message.reply_text(msg + "\n\nЗакрепить ещё слот за этим учеником? да или нет.")
            return True
        data["step"] = "username"
        await update.message.reply_text("🔒 Шаг 4/4 · @username ученика или минус (-)")
        return True
    if step == "username":
        student_username = "" if text == "-" else text.strip().lstrip("@")
        ok, msg = await db.add_blocked_slot(
            data["student_name"], data["day_of_week"], data["time"],
            student_username=student_username,
        )
        data["student_username"] = student_username
        data["slots_added"] = data.get("slots_added", 0) + 1
        data["step"] = "more_slot"
        await update.message.reply_text(msg + "\n\nЗакрепить ещё слот? да или нет.")
        return True
    if step == "more_slot":
        if text.lower() in ("да", "yes", "д", "y"):
            data["step"] = "day"
            await update.message.reply_text("🔒 День недели: пн, вт, ср, чт, пт, сб или вс")
            return True
        if text.lower() in ("нет", "no", "н", "n"):
            context.user_data.pop("block_slot", None)
            keyboard = [[InlineKeyboardButton("📅 Расписание", callback_data="tutor_schedule")]]
            await update.message.reply_text("✅ Готово.", reply_markup=InlineKeyboardMarkup(keyboard))
            return True
        await update.message.reply_text("Напиши да или нет.")
        return True
    return False


async def blocked_slot_link_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    data = context.user_data.get("blocked_slot_link_input")
    if not data:
        return False
    text = (update.message.text or "").strip()
    slot_id = data.get("slot_id")
    context.user_data.pop("blocked_slot_link_input", None)
    if text == "-":
        await db.update_blocked_slot_link(slot_id, "")
        await update.message.reply_text("✅ Ссылка у слота убрана.")
    else:
        if not text or len(text) < 5:
            await update.message.reply_text("Пришли полную ссылку или минус (-).")
            context.user_data["blocked_slot_link_input"] = data
            return True
        await db.update_blocked_slot_link(slot_id, text)
        await update.message.reply_text("✅ Ссылка сохранена. За минуту до времени слота бот отправит её ученику.")
    return True


async def lesson_link_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    data = context.user_data.get("lesson_link_input")
    if not data:
        return False
    text = (update.message.text or "").strip()
    lesson_id = data.get("lesson_id")
    context.user_data.pop("lesson_link_input", None)
    if text == "-":
        await db.update_lesson_link(lesson_id, "")
        await update.message.reply_text("✅ Ссылка убрана.")
    else:
        if not text or len(text) < 5:
            await update.message.reply_text("Ссылка слишком короткая или минус (-) чтобы убрать.")
            context.user_data["lesson_link_input"] = data
            return True
        await db.update_lesson_link(lesson_id, text)
        await update.message.reply_text("✅ Ссылка сохранена. За минуту до урока бот отправит её записанным.")
    return True


async def handle_callback(query, context: ContextTypes.DEFAULT_TYPE, data: str, user_id: int) -> bool:
    """Обрабатывает коллбэки расписания. Возвращает True если обработано."""
    if not data.startswith(("tutor_schedule", "tutor_clear", "tutor_block", "tutor_lesson_link", "unblock_", "blocked_slot_link_", "tutor_bookings_", "tutor_del_")):
        if data != "tutor_clear_chat_help":
            return False
    if data == "tutor_schedule":
        if not is_tutor(user_id, context.bot_data):
            await query.edit_message_text(MSG_ONLY_TUTOR)
            return True
        text, reply_markup = await _build_schedule_message(context)
        if len(text) > SCHEDULE_TEXT_MAX:
            text = text[: SCHEDULE_TEXT_MAX] + "\n\n…"
        try:
            await query.edit_message_text(text, reply_markup=reply_markup)
        except Exception as e:
            logger.warning("tutor_schedule edit_message_text failed: %s", e)
            try:
                await query.message.reply_text(text, reply_markup=reply_markup)
            except Exception:
                await query.edit_message_text("Расписание слишком большое. Задайте период.", reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN))
        return True
    if data == "tutor_schedule_set_range":
        if not is_tutor(user_id, context.bot_data):
            await query.edit_message_text(MSG_ONLY_TUTOR)
            return True
        _clear_other_flows(context, "schedule_range_input")
        context.user_data["schedule_range_input"] = {"step": "from"}
        await query.edit_message_text("📅 Шаг 1/2 · Начальная дата (ДД.ММ.ГГГГ):")
        return True
    if data == "tutor_schedule_clear_range":
        if not is_tutor(user_id, context.bot_data):
            await query.edit_message_text(MSG_ONLY_TUTOR)
            return True
        context.user_data.pop("schedule_range", None)
        text, reply_markup = await _build_schedule_message(context)
        if len(text) > 4090:
            text = text[:4080] + "\n\n…"
        await query.edit_message_text(text, reply_markup=reply_markup)
        return True
    if data.startswith("tutor_lesson_link_"):
        if not is_tutor(user_id, context.bot_data):
            await query.edit_message_text(MSG_ONLY_TUTOR)
            return True
        lesson_id = int(data.replace("tutor_lesson_link_", ""))
        lesson = await db.get_lesson(lesson_id)
        if not lesson:
            await query.answer("Урок не найден.")
            return True
        _clear_other_flows(context, "lesson_link_input")
        context.user_data["lesson_link_input"] = {"lesson_id": lesson_id}
        current = (lesson.get("lesson_link") or "").strip()
        prompt = f"🔗 Ссылка на урок «{lesson.get('title', 'Урок')}» ({lesson.get('lesson_date')} {lesson.get('lesson_time')})\n\nПришли ссылку или минус (-) чтобы убрать."
        if current:
            prompt += f"\n\nСейчас: {current[:60]}{'…' if len(current) > 60 else ''}"
        await query.edit_message_text(prompt)
        return True
    if data == "tutor_clear_lessons_only":
        if not is_tutor(user_id, context.bot_data):
            await query.edit_message_text(MSG_ONLY_TUTOR)
            return True
        keyboard = [
            [InlineKeyboardButton("✅ Подтвердить", callback_data="tutor_clear_lessons_confirm")],
            [InlineKeyboardButton("❌ Отмена", callback_data="tutor_clear_lessons_cancel")],
        ]
        await query.edit_message_text(
            "🗑 Удалить все уроки? Занятые слоты останутся.",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return True
    if data == "tutor_clear_lessons_confirm":
        if not is_tutor(user_id, context.bot_data):
            await query.edit_message_text(MSG_ONLY_TUTOR)
            return True
        lesson_ids = await db.get_all_lesson_ids()
        jq = context.application.job_queue
        if jq and jq.scheduler:
            for lid in lesson_ids:
                for name in (f"remind_1d_{lid}", f"remind_1h_{lid}"):
                    try:
                        jq.scheduler.remove_job(name)
                    except Exception:
                        pass
        n = await db.clear_lessons_only()
        text, reply_markup = await _build_schedule_message(context)
        await query.edit_message_text(f"✅ Удалено уроков: {n}.\n\n" + text, reply_markup=reply_markup)
        return True
    if data == "tutor_clear_lessons_cancel":
        if not is_tutor(user_id, context.bot_data):
            await query.edit_message_text(MSG_ONLY_TUTOR)
            return True
        await _refresh_schedule_message(query, context)
        return True
    if data == "tutor_clear_schedule":
        if not is_tutor(user_id, context.bot_data):
            await query.edit_message_text(MSG_ONLY_TUTOR)
            return True
        keyboard = [
            [InlineKeyboardButton("✅ Подтвердить", callback_data="tutor_clear_schedule_confirm")],
            [InlineKeyboardButton("❌ Отмена", callback_data="tutor_clear_schedule_cancel")],
        ]
        await query.edit_message_text(
            "🗑 Очистить всё расписание? Уроки, записи и слоты будут удалены.",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return True
    if data == "tutor_clear_schedule_confirm":
        if not is_tutor(user_id, context.bot_data):
            await query.edit_message_text(MSG_ONLY_TUTOR)
            return True
        lesson_ids = await db.get_all_lesson_ids()
        jq = context.application.job_queue
        if jq and jq.scheduler:
            for lid in lesson_ids:
                for name in (f"remind_1d_{lid}", f"remind_1h_{lid}"):
                    try:
                        jq.scheduler.remove_job(name)
                    except Exception:
                        pass
        n_lessons, n_slots = await db.clear_all_schedule()
        text, reply_markup = await _build_schedule_message(context)
        await query.edit_message_text(f"✅ Очищено: уроков {n_lessons}, слотов {n_slots}.\n\n" + text, reply_markup=reply_markup)
        return True
    if data == "tutor_clear_schedule_cancel":
        if not is_tutor(user_id, context.bot_data):
            await query.edit_message_text(MSG_ONLY_TUTOR)
            return True
        await _refresh_schedule_message(query, context)
        return True
    if data == "tutor_clear_chat_help":
        if not is_tutor(user_id, context.bot_data):
            await query.edit_message_text(MSG_ONLY_TUTOR)
            return True
        await query.answer()
        await query.message.reply_text(
            "💬 Как очистить чат: iPhone/Android — название бота вверху → Очистить историю. Desktop — правый клик по чату.",
            reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN),
        )
        return True
    if data == "tutor_block_slot":
        if not is_tutor(user_id, context.bot_data):
            await query.edit_message_text(MSG_ONLY_TUTOR)
            return True
        if context.user_data.get("block_slot"):
            await query.answer()
            await query.edit_message_text("🔒 Вы уже закрепляете слот. Продолжайте ввод или напишите «отмена».")
            return True
        _clear_other_flows(context, "block_slot")
        context.user_data["block_slot"] = {"step": "name"}
        await query.edit_message_text("🔒 Закрепить слот за учеником\n\nШаг 1/4 · Имя ученика:")
        return True
    if data.startswith("unblock_"):
        if not is_tutor(user_id, context.bot_data):
            await query.edit_message_text(MSG_ONLY_TUTOR)
            return True
        slot_id = int(data.split("_")[1])
        ok = await db.delete_blocked_slot(slot_id)
        if ok:
            await _refresh_schedule_message(query, context)
        else:
            await query.edit_message_text("Не удалось снять слот.", reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN))
        return True
    if data.startswith("blocked_slot_link_"):
        if not is_tutor(user_id, context.bot_data):
            await query.edit_message_text(MSG_ONLY_TUTOR)
            return True
        slot_id = int(data.split("_")[-1])
        _clear_other_flows(context, "blocked_slot_link_input")
        context.user_data["blocked_slot_link_input"] = {"slot_id": slot_id}
        await query.edit_message_text("🔗 Введите ссылку для этого слота (или «-» чтобы убрать):")
        return True
    if data.startswith("tutor_bookings_"):
        lesson_id = int(data.split("_")[2])
        if not is_tutor(user_id, context.bot_data):
            await query.edit_message_text(MSG_ONLY_TUTOR)
            return True
        bookings = await db.get_bookings_for_lesson(lesson_id)
        if not bookings:
            text = "👥 На этот урок пока никто не записан."
        else:
            lines = [f"   • {b.get('first_name') or b.get('username') or 'ID'+str(b['user_id'])} (id {b['user_id']})" for b in bookings]
            text = "👥 Кто записан\n\n" + "\n".join(lines)
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN))
        return True
    if data.startswith("tutor_del_"):
        lesson_id = int(data.split("_")[2])
        if not is_tutor(user_id, context.bot_data):
            await query.edit_message_text(MSG_ONLY_TUTOR)
            return True
        ok, lesson, user_ids = await db.delete_lesson(lesson_id)
        if ok and lesson:
            cancel_text = f"❌ Урок отменён\n\n▫️ {lesson['title']}\n📅 {lesson['lesson_date']}  ·  🕐 {lesson['lesson_time']}"
            for uid in user_ids:
                try:
                    await context.bot.send_message(chat_id=uid, text=cancel_text)
                except Exception:
                    pass
            jq = context.application.job_queue
            if jq and jq.scheduler:
                for name in (f"remind_1d_{lesson_id}", f"remind_1h_{lesson_id}"):
                    try:
                        jq.scheduler.remove_job(name)
                    except Exception:
                        pass
        await query.edit_message_text(
            "✅ Урок удалён." if ok else "❌ Не удалось удалить.",
            reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN),
        )
        return True
    return False

"""
Репетитор: создание уроков, сводка, заявки на время, рассылка ссылок.
"""
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import database as db

from config_loader import now_tz, localize_naive
from .common import (
    KEYBOARD_BACK_TO_MAIN,
    _clear_other_flows,
    format_lesson,
    is_tutor,
    MSG_ONLY_TUTOR,
    parse_date,
    parse_time,
    parse_max_students,
)
logger = logging.getLogger(__name__)


def _format_summary(day_date: str, lessons: list, blocked_today: list | None = None) -> str:
    parts = [f"📊 Сводка на сегодня ({day_date})\n\n"]
    if lessons:
        total_booked = sum(l.get("booked_count", 0) or 0 for l in lessons)
        parts.append(f"Уроков: {len(lessons)}  ·  Записано: {total_booked}\n\n")
        parts.append("\n\n".join(format_lesson(l, with_id=True) for l in lessons))
    else:
        parts.append("Уроков нет.\n\n")
    if blocked_today:
        parts.append("\n\n🔒 Закреплённые слоты на сегодня:\n")
        by_time = {}
        for b in blocked_today:
            t = (b.get("lesson_time") or "").strip()
            by_time.setdefault(t, []).append(b)
        for t in sorted(by_time.keys()):
            names = ", ".join(s["student_name"] for s in by_time[t])
            parts.append(f"   • {t} — {names}\n")
    if not lessons and not blocked_today:
        parts.append("Уроки на другие даты — в разделе «📅 Расписание».")
    return "".join(parts)


async def summary_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_tutor(update.effective_user.id, context.bot_data):
        await update.message.reply_text(MSG_ONLY_TUTOR)
        return
    now = now_tz()
    today = now.strftime("%Y-%m-%d")
    today_weekday = now.weekday()
    lessons = await db.get_lessons_on_date(today)
    all_blocked = await db.get_all_blocked_slots()
    blocked_today = [b for b in all_blocked if b["day_of_week"] == today_weekday]
    keyboard = [[InlineKeyboardButton("📅 Расписание", callback_data="tutor_schedule")]]
    keyboard.extend(KEYBOARD_BACK_TO_MAIN)
    await update.message.reply_text(
        _format_summary(today, lessons, blocked_today),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def daily_summary_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    now = now_tz()
    today = now.strftime("%Y-%m-%d")
    today_weekday = now.weekday()
    lessons = await db.get_lessons_on_date(today)
    all_blocked = await db.get_all_blocked_slots()
    blocked_today = [b for b in all_blocked if b["day_of_week"] == today_weekday]
    tutor_id = context.bot_data.get("tutor_user_id")
    if not tutor_id:
        return
    try:
        await context.bot.send_message(
            chat_id=tutor_id,
            text=_format_summary(today, lessons, blocked_today),
        )
    except Exception:
        pass


def _normalize_slot_time(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    parts = s.split(":")
    if len(parts) >= 2:
        try:
            h, m = int(parts[0]), int(parts[1])
            return f"{h:02d}:{m:02d}"
        except ValueError:
            return s
    return s


async def send_lesson_links_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    global_link = (context.bot_data.get("lesson_link") or "").strip()
    now = now_tz()
    target = now + timedelta(minutes=1)
    target_date = target.strftime("%Y-%m-%d")
    target_time = target.strftime("%H:%M")
    lessons = await db.get_lessons_at(target_date, target_time)
    for lesson in lessons:
        link = (lesson.get("lesson_link") or "").strip() or global_link
        if not link:
            continue
        bookings = await db.get_bookings_for_lesson(lesson["id"])
        title = lesson.get("title") or "Урок"
        msg = f"🕐 Через минуту начало: {title}\n\n👉 Ссылка на урок: {link}"
        for b in bookings:
            try:
                await context.bot.send_message(chat_id=b["user_id"], text=msg)
            except Exception:
                pass
    target_weekday = target.weekday()
    slots = await db.get_blocked_slots_for_day(target_weekday)
    for slot in slots:
        if _normalize_slot_time(slot.get("lesson_time") or "") != target_time:
            continue
        link = (slot.get("lesson_link") or "").strip()
        if not link:
            continue
        uid = slot.get("student_user_id")
        if not uid:
            continue
        student_name = (slot.get("student_name") or "").strip() or "Урок"
        msg = f"🕐 Через минуту начало: {student_name}\n\n👉 Ссылка: {link}"
        try:
            await context.bot.send_message(chat_id=uid, text=msg)
        except Exception:
            pass


async def _schedule_reminders(context: ContextTypes.DEFAULT_TYPE, lesson_id: int) -> None:
    lesson = await db.get_lesson(lesson_id)
    if not lesson:
        return
    try:
        dt = datetime.strptime(f"{lesson['lesson_date']} {lesson['lesson_time']}", "%Y-%m-%d %H:%M")
    except ValueError:
        return
    dt = localize_naive(dt)
    job_queue = context.application.job_queue
    if not job_queue:
        return
    when_1d = dt - timedelta(days=1)
    when_1h = dt - timedelta(hours=1)
    now = now_tz()
    if when_1d > now:
        job_queue.run_once(
            _reminder_callback,
            when_1d,
            data={"lesson_id": lesson_id, "kind": "1day"},
            name=f"remind_1d_{lesson_id}",
        )
    if when_1h > now:
        job_queue.run_once(
            _reminder_callback,
            when_1h,
            data={"lesson_id": lesson_id, "kind": "1hour"},
            name=f"remind_1h_{lesson_id}",
        )


async def _reminder_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    lesson_id = job.data.get("lesson_id")
    kind = job.data.get("kind", "")
    lesson = await db.get_lesson(lesson_id)
    if not lesson:
        return
    tutor_id = context.bot_data.get("tutor_user_id")
    text = (
        f"⏰ Напоминание: через {'1 день' if kind == '1day' else '1 час'} урок\n\n"
        f"▫️ {lesson['title']}\n📅 {lesson['lesson_date']}  ·  🕐 {lesson['lesson_time']}"
    )
    try:
        await context.bot.send_message(chat_id=tutor_id, text=text)
    except Exception:
        pass
    for b in await db.get_bookings_for_lesson(lesson_id):
        try:
            await context.bot.send_message(chat_id=b["user_id"], text=text)
        except Exception:
            pass


async def _post_lesson_to_channel(context: ContextTypes.DEFAULT_TYPE, lesson: dict, bot_username: str) -> None:
    channel_id = context.bot_data.get("channel_id")
    if not channel_id or not bot_username:
        return
    link = f"https://t.me/{bot_username.lstrip('@')}"
    text = f"📚 Новый урок\n\n▫️ {lesson['title']}\n📅 {lesson['lesson_date']}  ·  🕐 {lesson['lesson_time']}\n\nЗаписаться: {link}"
    try:
        await context.bot.send_message(chat_id=channel_id, text=text)
    except Exception:
        pass


async def _send_confirm_summary(update: Update, context: ContextTypes.DEFAULT_TYPE, data: dict) -> None:
    weeks = data.get("repeat_weeks", 1)
    times = data.get("times") or [data["time"]]
    summary = (
        f"✏️ Шаг 7/7 · Проверь\n\n▫️ {data['title']}\n"
        f"🕐 Время: {', '.join(times)}  ·  👥 мест: {data.get('max_students', 1)}\n"
    )
    if data.get("description"):
        summary += f"📝 {data['description']}\n"
    total = weeks * len(times)
    if weeks >= 2 or len(times) > 1:
        summary += f"\n📅 Будет создано уроков: {total}\n"
    summary += f"\n📅 Дата: {data['date']}" + (f" (и ещё {weeks - 1} нед.)" if weeks > 1 else "")
    if data.get("lesson_link"):
        summary += f"\n🔗 Ссылка: {data['lesson_link'][:50]}{'…' if len(data['lesson_link']) > 50 else ''}"
    summary += "\n\nСоздать? Напиши да или нет."
    await update.message.reply_text(summary)


async def _do_create_lessons(update: Update, context: ContextTypes.DEFAULT_TYPE, data: dict) -> None:
    weeks = data.get("repeat_weeks", 1)
    times = data.get("times") or [data["time"]]
    base_date = datetime.strptime(data["date"], "%Y-%m-%d").date()
    created = []
    for i in range(weeks):
        lesson_date = (base_date + timedelta(weeks=i)).strftime("%Y-%m-%d")
        for t in times:
            lesson_id = await db.add_lesson(
                title=data["title"],
                lesson_date=lesson_date,
                lesson_time=t,
                max_students=data.get("max_students", 1),
                description=data.get("description", ""),
                lesson_link=data.get("lesson_link", ""),
            )
            await _schedule_reminders(context, lesson_id)
            created.append((lesson_id, lesson_date, t))
    if context.bot_data.get("channel_id") and created:
        lesson = await db.get_lesson(created[0][0])
        if lesson:
            await _post_lesson_to_channel(context, lesson, context.bot_data.get("bot_username", ""))
    n = len(created)
    if n == 1:
        await update.message.reply_text(f"✅ Урок создан (ID {created[0][0]}). Ученики видят в /lessons.")
    else:
        sample = ", ".join(f"{d} {t}" for _, d, t in created[:5])
        if n > 5:
            sample += f" … ещё {n - 5}"
        await update.message.reply_text(f"✅ Создано уроков: {n}\n\n{sample}")


async def add_lesson_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_tutor(update.effective_user.id, context.bot_data):
        await update.message.reply_text(MSG_ONLY_TUTOR)
        return
    _clear_other_flows(context, "add_lesson")
    context.user_data["add_lesson"] = {"step": "title"}
    await update.message.reply_text(
        "✏️ Создание урока\n\nШаг 1/7 · Название\nНапиши название урока, например: Математика, 8 класс",
    )


async def add_lesson_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_tutor(user_id, context.bot_data):
        return
    data = context.user_data.get("add_lesson")
    if not data:
        return
    text = (update.message.text or "").strip()
    step = data.get("step", "title")

    if step == "title":
        data["title"] = text
        data["step"] = "date"
        await update.message.reply_text("✏️ Шаг 2/7 · Дата (20.02.2025 или 2025-02-20)")
        return
    if step == "date":
        date = parse_date(text)
        if not date:
            await update.message.reply_text("❌ Неверный формат. Пример: 20.02.2025")
            return
        data["date"] = date
        data["step"] = "time"
        await update.message.reply_text("✏️ Шаг 3/7 · Время начала (14:00)")
        return
    if step == "time":
        time = parse_time(text)
        if not time:
            await update.message.reply_text("❌ Пример: 14:00")
            return
        data["time"] = time
        data["times"] = [time]
        data["step"] = "more_time"
        await update.message.reply_text("✏️ Ещё время в этот день? Напиши время или минус (-)")
        return
    if step == "more_time":
        if text.strip() == "-":
            data["step"] = "max_students"
            await update.message.reply_text("✏️ Шаг 4/7 · Мест на урок (1–100)")
            return
        time = parse_time(text)
        if not time:
            await update.message.reply_text("❌ Пример: 10:00 или минус (-)")
            return
        data["times"].append(time)
        await update.message.reply_text(f"Сейчас: {', '.join(data['times'])}\nЕщё время или минус (-):")
        return
    if step == "max_students":
        n = parse_max_students(text)
        if n is None:
            await update.message.reply_text("❌ Введи число от 1 до 100.")
            return
        data["max_students"] = n
        data["step"] = "description"
        await update.message.reply_text("✏️ Шаг 5/7 · Описание или минус (-)")
        return
    if step == "description":
        data["description"] = text if text != "-" else ""
        data["step"] = "repeat"
        await update.message.reply_text("✏️ Шаг 6/7 · Повторять еженедельно? да/нет")
        return
    if step == "repeat":
        if text.lower() in ("да", "yes", "д", "y"):
            data["step"] = "repeat_weeks"
            await update.message.reply_text("✏️ Сколько недель? (2–52)")
            return
        data["repeat_weeks"] = 1
        data["step"] = "link"
        await update.message.reply_text("✏️ Ссылка на урок (Zoom, Meet) или минус (-)")
        return
    if step == "repeat_weeks":
        try:
            n = int(text.strip())
            if 2 <= n <= 52:
                data["repeat_weeks"] = n
                data["step"] = "link"
                await update.message.reply_text("✏️ Ссылка на урок или минус (-)")
                return
        except ValueError:
            pass
        await update.message.reply_text("❌ Введи число от 2 до 52.")
        return
    if step == "link":
        data["lesson_link"] = text.strip() if text != "-" else ""
        data["step"] = "confirm"
        await _send_confirm_summary(update, context, data)
        return
    if step == "confirm":
        if text.lower() in ("да", "yes", "д", "y"):
            weeks = data.get("repeat_weeks", 1)
            times = data.get("times") or [data["time"]]
            base_date = datetime.strptime(data["date"], "%Y-%m-%d").date()
            blocked_names_by_dt = []
            for i in range(weeks):
                d = base_date + timedelta(weeks=i)
                for t in times:
                    slots = await db.get_blocked_slots(d.weekday(), t)
                    if slots:
                        names = ", ".join(s["student_name"] for s in slots)
                        blocked_names_by_dt.append((d.strftime("%d.%m"), t, names))
            if blocked_names_by_dt:
                parts = [f"{d} {t} — {names}" for d, t, names in blocked_names_by_dt[:5]]
                msg = "В это время закреплено за: " + "; ".join(parts)
                if len(blocked_names_by_dt) > 5:
                    msg += " …"
                msg += "\n\nОбъединить урок? да/нет"
                data["step"] = "confirm_merge"
                await update.message.reply_text(msg)
                return
            await _do_create_lessons(update, context, data)
            context.user_data.pop("add_lesson", None)
            return
        await update.message.reply_text("Отменено.")
        context.user_data.pop("add_lesson", None)
        return
    if step == "confirm_merge":
        if text.lower() in ("да", "yes", "д", "y"):
            await _do_create_lessons(update, context, data)
        else:
            await update.message.reply_text("Отменено.")
        context.user_data.pop("add_lesson", None)
        return


async def handle_callback(query, context: ContextTypes.DEFAULT_TYPE, data: str, user_id: int) -> bool:
    if data == "tutor_summary":
        if not is_tutor(user_id, context.bot_data):
            await query.edit_message_text(MSG_ONLY_TUTOR)
            return True
        now = now_tz()
        today = now.strftime("%Y-%m-%d")
        today_weekday = now.weekday()
        lessons = await db.get_lessons_on_date(today)
        all_blocked = await db.get_all_blocked_slots()
        blocked_today = [b for b in all_blocked if b["day_of_week"] == today_weekday]
        keyboard = [[InlineKeyboardButton("📅 Расписание", callback_data="tutor_schedule")]]
        keyboard.extend(KEYBOARD_BACK_TO_MAIN)
        await query.edit_message_text(
            _format_summary(today, lessons, blocked_today),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return True
    if data == "tutor_freetime_requests":
        if not is_tutor(user_id, context.bot_data):
            await query.edit_message_text(MSG_ONLY_TUTOR)
            return True
        requests_list = await db.get_free_time_requests(limit=30)
        if not requests_list:
            await query.edit_message_text(
                "📬 Заявки на свободное время\n\nПока нет заявок.",
                reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN),
            )
            return True
        lines = []
        for r in requests_list:
            name = (r.get("first_name") or r.get("username") or f"ID{r['user_id']}").strip()
            if (r.get("username") or "").strip():
                name += f" @{r['username']}"
            lines.append(f"• {name} — {r['requested_date']} в {r['requested_time']}")
        text = "📬 Заявки на свободное время\n\n" + "\n".join(lines)
        if len(text) > 4000:
            text = text[:3990] + "\n\n…"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(KEYBOARD_BACK_TO_MAIN))
        return True
    if data == "tutor_add_lesson":
        if not is_tutor(user_id, context.bot_data):
            await query.edit_message_text(MSG_ONLY_TUTOR)
            return True
        _clear_other_flows(context, "add_lesson")
        context.user_data["add_lesson"] = {"step": "title"}
        await query.edit_message_text(
            "✏️ Создание урока\n\nШаг 1/7 · Название\nНапиши название урока:",
        )
        return True
    return False
